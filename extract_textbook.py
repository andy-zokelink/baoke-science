"""
科学六年级上教科版 PDF 提取脚本
用 pdf2image 转图片 → Gemini 2.5 Flash 识别 → 存入数据库

Gemini API 兼容 OpenAI 格式：https://ai-api.kkidc.com/v1/chat/completions
模型: gemini-2.5-flash
"""
import sys, os, json, time, sqlite3, base64, io, re, argparse
from pathlib import Path

# Windows 路径处理
PDF_PATH = r"C:\Users\HermesCC\.hermes\cache\documents\doc_5ebc6c9c7caf_科学六年级上教科版.pdf"
DB_PATH = r"C:\Users\HermesCC\baoke-science\baoke_learning.db"
OUTPUT_DIR = r"C:\Users\HermesCC\baoke-science\textbook_extracted"
API_URL = "https://ai-api.kkidc.com/v1/chat/completions"
MODEL = "gemini-2.5-flash"
# 从 Hermes config 或环境变量读取 API KEY
import yaml as _yaml
_hermes_config_path = os.path.expanduser("~/.hermes/config.yaml")
if os.path.exists(_hermes_config_path):
    with open(_hermes_config_path) as _f:
        _cfg = _yaml.safe_load(_f)
    _aux_vision = _cfg.get("auxiliary", {}).get("vision", {})
    API_KEY = _aux_vision.get("api_key", "") or os.environ.get("KKIDC_API_KEY", "")
else:
    API_KEY = os.environ.get("KKIDC_API_KEY", "")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══ 数据库操作 ═══

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_or_create_material():
    """注册教材为新的素材源"""
    with get_conn() as conn:
        # 先查有没有已存在的
        existing = conn.execute(
            "SELECT id FROM source_materials WHERE title=? AND material_type_id IN (SELECT id FROM material_types WHERE name=?)",
            ("科学六年级上教科版", "教材")
        ).fetchone()
        if existing:
            print(f"素材已存在，ID={existing['id']}")
            return existing['id']
        
        # 看有没有 '教材' 这个类型
        mt = conn.execute("SELECT id FROM material_types WHERE name='教材'").fetchone()
        if not mt:
            c = conn.execute("INSERT INTO material_types (name) VALUES ('教材')")
            mt_id = c.lastrowid
            print(f"新建素材类型: 教材 (ID={mt_id})")
        else:
            mt_id = mt['id']
        
        conn.execute('''INSERT INTO source_materials 
            (title, file_path, file_type, page_count, material_type_id, course_id)
            VALUES (?,?,?,?,?,?)''',
            ("科学六年级上教科版", PDF_PATH, "pdf", 40, mt_id, 1))
        conn.commit()
        mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"注册素材: ID={mid}")
        
        # 创建教材特定的概念分组：按单元
        units = [
            "微小世界", "物质的变化", "宇宙", 
            "环境和我们", "工具与技术"
        ]
        # 获取现有概念类型ID
        for ct_name in ["核心概念", "常考概念", "易错概念", "边缘概念"]:
            ct = conn.execute("SELECT id FROM concept_types WHERE name=?", (ct_name,)).fetchone()
            if not ct:
                conn.execute("INSERT INTO concept_types (name) VALUES (?)", (ct_name,))
        conn.commit()
        
        return mid

def save_page_result(material_id, page_num, raw_text):
    """保存页面提取结果到 source_pages"""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM source_pages WHERE material_id=? AND page_number=?",
            (material_id, page_num)
        ).fetchone()
        if existing:
            conn.execute('''UPDATE source_pages SET ocr_text=?, ocr_method='gemini_vision', processed_at=CURRENT_TIMESTAMP
                WHERE material_id=? AND page_number=?''',
                (raw_text, material_id, page_num))
            return existing['id']
        else:
            c = conn.execute('''INSERT INTO source_pages 
                (material_id, page_number, ocr_text, ocr_method, processed_at)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP)''',
                (material_id, page_num, raw_text, 'gemini_vision'))
            return c.lastrowid

def save_questions(questions_dict):
    """将解析出的题目保存到 raw_questions + student_answers"""
    if not questions_dict:
        return 0
    count = 0
    with get_conn() as conn:
        # 获取题型映射
        qt_map = {}
        for r in conn.execute("SELECT id, name FROM question_types").fetchall():
            qt_map[r['name']] = r['id']
        # 确保题型存在
        for qn in ["填空题", "选择题", "判断题", "简答题", "实验题", "作图题", "连线题"]:
            if qn not in qt_map:
                c = conn.execute("INSERT INTO question_types (name) VALUES (?)", (qn,))
                qt_map[qn] = c.lastrowid
        
        sid = 1  # student_id = 1 (Harry)
        
        for item in questions_dict:
            for k, v in item.items():
                if k.startswith("q") or k == "questions" or k == "items":
                    if isinstance(v, list):
                        for q in v:
                            count += _insert_one_question(conn, q, sid, qt_map)
                    elif isinstance(v, dict):
                        count += _insert_one_question(conn, v, sid, qt_map)
                elif isinstance(v, dict) and ("题目" in v or "question" in v or "题号" in v):
                    count += _insert_one_question(conn, v, sid, qt_map)
        conn.commit()
    return count

def _insert_one_question(conn, q, sid, qt_map):
    """插入单条题目"""
    if not q or not isinstance(q, dict):
        return 0
    
    qtext = q.get("题目", q.get("question", q.get("问题", "")))
    if not qtext:
        return 0
    
    qnum = str(q.get("题号", q.get("number", q.get("序号", ""))))
    correct = q.get("答案", q.get("correct_answer", q.get("correct", "")))
    qtype_name = q.get("题型", q.get("qtype", q.get("type", "")))
    kp = q.get("知识点", q.get("knowledge_point", q.get("knowledge", "")))
    options = q.get("选项", q.get("options", q.get("choices", None)))
    difficulty = q.get("难度", q.get("difficulty", 3))
    score = q.get("分值", q.get("score", 1))
    unit = q.get("单元", q.get("unit", ""))
    
    if isinstance(options, list):
        options = json.dumps(options, ensure_ascii=False)
    elif options and isinstance(options, str):
        options = options  # keep as is
    
    # 推断题型
    if not qtype_name:
        if options and any(o.startswith(("A", "A.")) for o in (options if isinstance(options, list) else json.loads(options)) if isinstance(o, str)):
            qtype_name = "选择题"
        elif "____" in qtext or "（  ）" in qtext or "______" in qtext:
            qtype_name = "填空题"
        elif any(kw in qtext for kw in ["判断", "是否正确", "√", "×"]):
            qtype_name = "判断题"
        elif "连线" in qtext or "连一连" in qtext:
            qtype_name = "连线题"
        elif "实验" in qtext:
            qtype_name = "实验题"
        else:
            qtype_name = "简答题"
    
    qt_id = qt_map.get(qtype_name, qt_map.get("简答题"))
    
    # 查找或创建知识点对应的概念
    concept_id = None
    if kp:
        existing = conn.execute("SELECT id FROM concepts WHERE name=? AND course_id=1", (kp,)).fetchone()
        if existing:
            concept_id = existing['id']
        else:
            # 自动创建概念
            ct_id = conn.execute("SELECT id FROM concept_types WHERE name='常考概念'").fetchone()
            if ct_id:
                c2 = conn.execute('''INSERT INTO concepts 
                    (name, definition, concept_type_id, course_id, unit)
                    VALUES (?,?,?,?,?)''',
                    (kp, "", ct_id['id'], 1, unit))
                concept_id = c2.lastrowid
                print(f"  新建概念: {kp} (ID={concept_id}, 单元={unit or '未分类'})")
    
    # 插入 raw_questions
    tags = json.dumps({"unit": unit} if unit else {}, ensure_ascii=False)
    
    conn.execute('''INSERT INTO raw_questions 
        (question_number, question_text, question_type_id, options, correct_answer,
         difficulty, score_value, knowledge_point, concept_id, tags, raw_response_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (qnum, qtext, qt_id, options, correct,
         difficulty, score, kp, concept_id, tags, 
         json.dumps(q, ensure_ascii=False)))
    
    qid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    print(f"  [ID={qid}] [{qtype_name}] 题{qnum}: {qtext[:40]}...")
    return 1

def save_concept_from_page(raw_text, unit_name):
    """从页面提取的结构化概念保存到数据库"""
    try:
        data = json.loads(raw_text)
    except:
        return 0, 0
    
    # 如果返回有 concepts 字段
    concepts = data.get("concepts", data.get("knowledge_points", data.get("learning_goals", [])))
    if isinstance(concepts, dict):
        concepts = [{"name": k, "definition": v} for k, v in concepts.items()]
    
    count = 0
    with get_conn() as conn:
        ct_map = {}
        for r in conn.execute("SELECT id, name FROM concept_types").fetchall():
            ct_map[r['name']] = r['id']
        
        default_ct_id = ct_map.get("常考概念")
        core_ct_id = ct_map.get("核心概念")
        
        for c in concepts:
            if isinstance(c, str):
                name = c
                ctype = "常考概念"
            elif isinstance(c, dict):
                name = c.get("name", c.get("概念", c.get("知识点", "")))
                ctype = c.get("type", c.get("概念类型", "常考概念"))
            else:
                continue
            
            if not name:
                continue
            
            # 检查是否已存在
            existing = conn.execute("SELECT id FROM concepts WHERE name=? AND course_id=1", (name,)).fetchone()
            if existing:
                continue
            
            ct_id = ct_map.get(ctype, default_ct_id)
            definition = c.get("definition", c.get("定义", "")) if isinstance(c, dict) else ""
            analogy = c.get("analogy", c.get("类比", "")) if isinstance(c, dict) else ""
            example = c.get("example", c.get("例子", "")) if isinstance(c, dict) else ""
            
            conn.execute('''INSERT INTO concepts 
                (name, definition, analogy, example, concept_type_id, course_id, unit)
                VALUES (?,?,?,?,?,?,?)''',
                (name, definition, analogy, example, ct_id, 1, unit_name))
            count += 1
            print(f"  概念入库: {name} ({ctype})")
        
        conn.commit()
    return count

# ═══ PDF 图片转换 ═══

def pdf_to_images(pdf_path, output_dir, dpi=200):
    """将 PDF 转成图片"""
    from pdf2image import convert_from_path
    
    print(f"转换 PDF → 图片 (dpi={dpi})...")
    images = convert_from_path(pdf_path, dpi=dpi, fmt='jpeg')
    print(f"共 {len(images)} 页")
    
    image_paths = []
    for i, img in enumerate(images):
        path = os.path.join(output_dir, f"page_{i+1:03d}.jpg")
        img.save(path, "JPEG", quality=85)
        image_paths.append(path)
        print(f"  第{i+1}页: {path}")
    
    return image_paths

# ═══ Gemini API 调用 ═══

def image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def call_gemini_vision(image_path, prompt, retries=3):
    """调用 Gemini 2.5 Flash 识别图片内容"""
    import urllib.request
    
    b64 = image_to_base64(image_path)
    
    # 获取文件扩展名对应的 MIME
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")
    
    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                ]
            }
        ],
        "temperature": 0.1,
        "max_tokens": 8192
    }
    
    data = json.dumps(body).encode("utf-8")
    
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API_URL,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {API_KEY}"
                }
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                return content
        except Exception as e:
            last_err = e
            print(f"  重试 {attempt+1}/{retries}: {e}")
            time.sleep(3 * (attempt + 1))
    
    raise last_err

# ═══ 提示词 ═══

STRUCTURE_PROMPT = """你是中国小学科学教育专家。请分析这张教科版六年级上册科学教材的页面，输出JSON格式。

先看这是教材的什么内容：
- 如果是**封面/扉页/目录**：输出目录结构，包含各单元名称和课时
- 如果是**单元首页**：输出单元名称、本单元要学习的核心概念
- 如果是**正文（知识点+实验）**：输出知识点、概念、定义
- 如果是**练习题/活动手册**：输出每一道题的完整信息

请严格按以下JSON格式输出：
{
  "page_type": "封面|目录|单元首页|正文|练习|活动|空白页",
  "unit": "单元名称（若有）",
  "content_summary": "本页内容概述",
  "concepts": [
    {
      "name": "概念名称",
      "definition": "精确定义（30字以内）",
      "type": "核心概念|常考概念|易错概念",
      "unit": "所属单元"
    }
  ],
  "questions": [
    {
      "题号": "1",
      "题型": "填空题|选择题|判断题|简答题|实验题|连线题",
      "题目": "完整题目文本",
      "选项": ["A.xxx", "B.xxx"]（选择题才有）,
      "答案": "正确答案",
      "知识点": "考察的知识点",
      "难度": 3,
      "单元": "所属单元",
      "分值": 1
    }
  ],
  "key_knowledge": "本页最重要的知识点总结"
}

注意：
1. 练习题中的每个小题都要单独列出
2. 概念定义要准确、精炼
3. 知识点名称要和已有知识体系保持一致
4. 如果页面有实验/活动，也要提取知识点
5. 题目中如果有图片/图表，在题目文本中注明【图:描述】
6. 选择题的选项要逐个列出"""

def process_pdf():
    """主处理流程"""
    print("=" * 60)
    print("科学六年级上教科版 PDF 提取")
    print("=" * 60)
    
    # 注册教材源
    material_id = get_or_create_material()
    print(f"\n素材ID: {material_id}")
    
    # 已渲染过图片（检查缓存）
    image_dir = os.path.join(OUTPUT_DIR, "images")
    os.makedirs(image_dir, exist_ok=True)
    
    existing_images = sorted([f for f in os.listdir(image_dir) if f.endswith('.jpg')])
    
    if len(existing_images) >= 40:
        print(f"使用已有图片缓存: {len(existing_images)} 张")
        image_paths = [os.path.join(image_dir, f"page_{i+1:03d}.jpg") for i in range(40)]
    else:
        image_paths = pdf_to_images(PDF_PATH, image_dir, dpi=200)
    
    total_questions = 0
    total_concepts = 0
    results = []
    
    for idx, img_path in enumerate(image_paths):
        page_num = idx + 1
        print(f"\n{'='*40}")
        print(f"处理第 {page_num}/40 页: {os.path.basename(img_path)}")
        print(f"{'='*40}")
        
        try:
            raw = call_gemini_vision(img_path, STRUCTURE_PROMPT)
            
            # 清理可能的 markdown 代码块包裹
            raw_clean = raw.strip()
            if raw_clean.startswith("```"):
                raw_clean = re.sub(r'^```\w*\n?', '', raw_clean)
                raw_clean = re.sub(r'\n```$', '', raw_clean)
            
            # 保存原始结果
            sp_id = save_page_result(material_id, page_num, raw_clean)
            results.append({"page": page_num, "content": raw_clean, "source_page_id": sp_id})
            
            # 解析 JSON 并入库
            try:
                data = json.loads(raw_clean)
                page_type = data.get("page_type", "")
                unit = data.get("unit", "")
                concepts = data.get("concepts", [])
                questions = data.get("questions", [])
                
                print(f"  类型: {page_type} | 单元: {unit}")
                
                if concepts:
                    c_count = 0
                    with get_conn() as conn:
                        ct_map = {}
                        for r in conn.execute("SELECT id, name FROM concept_types").fetchall():
                            ct_map[r['name']] = r['id']
                        for c in concepts:
                            name = c.get("name", "")
                            if not name:
                                continue
                            existing = conn.execute("SELECT id FROM concepts WHERE name=? AND course_id=1", (name,)).fetchone()
                            if existing:
                                continue
                            ct_name = c.get("type", "常考概念")
                            ct_id = ct_map.get(ct_name, ct_map.get("常考概念"))
                            defn = c.get("definition", "")
                            conn.execute('''INSERT INTO concepts (name, definition, concept_type_id, course_id, unit)
                                VALUES (?,?,?,?,?)''',
                                (name, defn, ct_id, 1, unit or "未分类"))
                            c_count += 1
                        conn.commit()
                    total_concepts += c_count
                    print(f"  新增概念: {c_count}")
                
                if questions:
                    q_count = 0
                    with get_conn() as conn:
                        qt_map = {}
                        for r in conn.execute("SELECT id, name FROM question_types").fetchall():
                            qt_map[r['name']] = r['id']
                        for qn in ["填空题", "选择题", "判断题", "简答题", "实验题", "连线题"]:
                            if qn not in qt_map:
                                c = conn.execute("INSERT INTO question_types (name) VALUES (?)", (qn,))
                                qt_map[qn] = c.lastrowid
                        
                        for q in questions:
                            qtext = q.get("题目", q.get("question", ""))
                            if not qtext:
                                continue
                            qnum = str(q.get("题号", ""))
                            correct = q.get("答案", "")
                            kp = q.get("知识点", "")
                            unit_name = q.get("单元", unit)
                            qtype_name = q.get("题型", "")
                            options = q.get("选项", None)
                            difficulty = q.get("难度", 3)
                            score = q.get("分值", 1)
                            
                            # 推断题型
                            if not qtype_name:
                                if options and len(options) > 0:
                                    qtype_name = "选择题"
                                elif "____" in qtext or "（  ）" in qtext:
                                    qtype_name = "填空题"
                                elif any(kw in qtext for kw in ["判断", "√", "×"]):
                                    qtype_name = "判断题"
                                elif "连线" in qtext:
                                    qtype_name = "连线题"
                                else:
                                    qtype_name = "简答题"
                            
                            qt_id = qt_map.get(qtype_name)
                            if isinstance(options, list):
                                options = json.dumps(options, ensure_ascii=False)
                            
                            # 找概念
                            concept_id = None
                            if kp:
                                existing_c = conn.execute("SELECT id FROM concepts WHERE name=? AND course_id=1", (kp,)).fetchone()
                                if existing_c:
                                    concept_id = existing_c['id']
                            
                            tags = json.dumps({"unit": unit_name} if unit_name else {}, ensure_ascii=False)
                            conn.execute('''INSERT INTO raw_questions 
                                (source_page_id, material_id, course_id, question_number, question_text,
                                 question_type_id, options, correct_answer, difficulty, score_value,
                                 knowledge_point, concept_id, tags, raw_response_json)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                (sp_id, material_id, 1, qnum, qtext,
                                 qt_id, options, correct, difficulty, score,
                                 kp, concept_id, tags, json.dumps(q, ensure_ascii=False)))
                            q_count += 1
                        conn.commit()
                    total_questions += q_count
                    print(f"  新增题目: {q_count}")
                
            except json.JSONDecodeError as e:
                print(f"  JSON解析失败: {e}")
                print(f"  前100字符: {raw_clean[:100]}")
                # 即使解析失败，原始内容已保存在 source_pages 中
            
            # 保存到本地 JSON（备份）
            result_file = os.path.join(OUTPUT_DIR, f"page_{page_num:03d}.json")
            with open(result_file, "w", encoding="utf-8") as f:
                f.write(raw_clean)
            print(f"  已保存: {result_file}")
            
            time.sleep(1)  # 节流
            
        except Exception as e:
            print(f"  处理失败: {e}")
            # 保存错误信息
            save_page_result(material_id, page_num, json.dumps({
                "page_type": "error",
                "error": str(e),
                "page": page_num
            }))
    
    print(f"\n{'='*60}")
    print(f"处理完成!")
    print(f"  总页数: 40")
    print(f"  新增概念: {total_concepts}")
    print(f"  新增题目: {total_questions}")
    print(f"{'='*60}")
    
    return results, material_id

# ═══ 提取并打包成 Claude Code 可消费的格式 ═══

def generate_textbook_json(results, output_path):
    """将提取结果打包成单一 JSON，供 Claude Code 消费"""
    combined = []
    for r in results:
        combined.append({
            "page": r["page"],
            "content": r["content"]
        })
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    
    print(f"教材提取JSON已保存: {output_path}")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="提取教科版科学六年级上册PDF")
    parser.add_argument("--steps", choices=["extract", "import", "full"], default="full",
                       help="extract=仅提取到JSON, import=仅从JSON导入DB, full=完整流程")
    parser.add_argument("--from-json", help="从已有JSON批量导入DB")
    
    args = parser.parse_args()
    
    if args.steps == "extract":
        # 仅提取，不导入数据库
        print("模式: 仅提取（不导入DB）")
        material_id = get_or_create_material()
        image_dir = os.path.join(OUTPUT_DIR, "images")
        os.makedirs(image_dir, exist_ok=True)
        existing = sorted([f for f in os.listdir(image_dir) if f.endswith('.jpg')])
        if len(existing) < 40:
            pdf_to_images(PDF_PATH, image_dir, dpi=200)
        
        results = []
        all_data = []
        for pn in range(1, 41):
            img_path = os.path.join(image_dir, f"page_{pn:03d}.jpg")
            if not os.path.exists(img_path):
                print(f"跳页 {pn}: 图片不存在")
                continue
            print(f"\n第 {pn}/40 页")
            raw = call_gemini_vision(img_path, STRUCTURE_PROMPT)
            raw_clean = raw.strip()
            if raw_clean.startswith("```"):
                raw_clean = re.sub(r'^```\w*\n?', '', raw_clean)
                raw_clean = re.sub(r'\n```$', '', raw_clean)
            all_data.append({"page": pn, "content": raw_clean})
            result_file = os.path.join(OUTPUT_DIR, f"page_{pn:03d}.json")
            with open(result_file, "w", encoding="utf-8") as f:
                f.write(raw_clean)
            time.sleep(1)
        
        output = os.path.join(OUTPUT_DIR, "all_pages.json")
        with open(output, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"\n全部提取完成: {output}")
        
    elif args.steps == "import" or (args.steps == "full" and args.from_json):
        # 从已有JSON导入DB
        json_path = args.from_json or os.path.join(OUTPUT_DIR, "all_pages.json")
        print(f"模式: 从JSON导入DB ({json_path})")
        with open(json_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
        
        material_id = get_or_create_material()
        total_q = 0
        total_c = 0
        
        for entry in all_data:
            pn = entry["page"]
            raw_clean = entry["content"]
            
            sp_id = save_page_result(material_id, pn, raw_clean)
            
            try:
                data = json.loads(raw_clean)
                unit = data.get("unit", "")
                concepts = data.get("concepts", [])
                questions = data.get("questions", [])
                
                # 概念入库
                if concepts:
                    with get_conn() as conn:
                        ct_map = {}
                        for r in conn.execute("SELECT id, name FROM concept_types").fetchall():
                            ct_map[r['name']] = r['id']
                        for c in concepts:
                            name = c.get("name", "")
                            if not name:
                                continue
                            existing = conn.execute("SELECT id FROM concepts WHERE name=? AND course_id=1", (name,)).fetchone()
                            if existing:
                                continue
                            ct_name = c.get("type", "常考概念")
                            ct_id = ct_map.get(ct_name, ct_map.get("常考概念"))
                            defn = c.get("definition", "")
                            conn.execute('''INSERT INTO concepts (name, definition, concept_type_id, course_id, unit)
                                VALUES (?,?,?,?,?)''',
                                (name, defn, ct_id, 1, unit or "未分类"))
                            total_c += 1
                        conn.commit()
                
                # 题目入库
                if questions:
                    with get_conn() as conn:
                        qt_map = {}
                        for r in conn.execute("SELECT id, name FROM question_types").fetchall():
                            qt_map[r['name']] = r['id']
                        for qn in ["填空题", "选择题", "判断题", "简答题", "实验题", "连线题"]:
                            if qn not in qt_map:
                                c = conn.execute("INSERT INTO question_types (name) VALUES (?)", (qn,))
                                qt_map[qn] = c.lastrowid
                        
                        for q in questions:
                            qtext = q.get("题目", "")
                            if not qtext:
                                continue
                            qnum = str(q.get("题号", ""))
                            correct = q.get("答案", "")
                            kp = q.get("知识点", "")
                            unit_name = q.get("单元", unit)
                            qtype_name = q.get("题型", "")
                            options = q.get("选项", None)
                            difficulty = q.get("难度", 3)
                            score = q.get("分值", 1)
                            
                            if not qtype_name:
                                if options and len(options) > 0:
                                    qtype_name = "选择题"
                                elif "____" in qtext or "（  ）" in qtext:
                                    qtype_name = "填空题"
                                elif any(kw in qtext for kw in ["判断", "√", "×"]):
                                    qtype_name = "判断题"
                                elif "连线" in qtext:
                                    qtype_name = "连线题"
                                else:
                                    qtype_name = "简答题"
                            
                            qt_id = qt_map.get(qtype_name)
                            if isinstance(options, list):
                                options = json.dumps(options, ensure_ascii=False)
                            
                            concept_id = None
                            if kp:
                                existing_c = conn.execute("SELECT id FROM concepts WHERE name=? AND course_id=1", (kp,)).fetchone()
                                if existing_c:
                                    concept_id = existing_c['id']
                            
                            tags = json.dumps({"unit": unit_name} if unit_name else {}, ensure_ascii=False)
                            conn.execute('''INSERT INTO raw_questions 
                                (source_page_id, material_id, course_id, question_number, question_text,
                                 question_type_id, options, correct_answer, difficulty, score_value,
                                 knowledge_point, concept_id, tags, raw_response_json)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                (sp_id, material_id, 1, qnum, qtext,
                                 qt_id, options, correct, difficulty, score,
                                 kp, concept_id, tags, json.dumps(q, ensure_ascii=False)))
                            total_q += 1
                        conn.commit()
                
                print(f"  第{pn}页: 概念+{total_c} 题目+{total_q} (累计)")
            except json.JSONDecodeError:
                print(f"  第{pn}页: JSON解析失败，跳过")
        
        print(f"\n导入完成! 新增概念: {total_c} 新增题目: {total_q}")
        
    else:
        # 完整流程：提取 → 导入DB
        print("模式: 完整流程（提取+导入DB）")
        results, material_id = process_pdf()
        
        # 生成汇总JSON
        output = os.path.join(OUTPUT_DIR, "all_pages.json")
        generate_textbook_json(results, output)
        
        # 汇总统计
        print(f"\n材料ID: {material_id}")
        print(f"教材原始页面: {OUTPUT_DIR}/page_*.json")
        print(f"汇总JSON: {output}")
