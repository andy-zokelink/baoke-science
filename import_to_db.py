"""
从提取的 JSON 批处理导入概念+题目到数据库
"""
import json, os, sqlite3, re

DB_PATH = r"C:\Users\HermesCC\baoke-science\baoke_learning.db"
OUTPUT_DIR = r"C:\Users\HermesCC\baoke-science\textbook_extracted"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# 读取所有 page JSON
results = []
for pn in range(1, 41):
    jp = os.path.join(OUTPUT_DIR, f"page_{pn:03d}.json")
    if os.path.exists(jp) and os.path.getsize(jp) > 100:
        with open(jp, encoding="utf-8") as f:
            raw = f.read().strip()
        results.append({"page": pn, "content": raw})

print(f"读取 {len(results)} 个页面 JSON")

# 统计
total_questions = 0
total_concepts = 0
new_questions = 0
new_concepts = 0

with get_conn() as conn:
    # 1. 获取映射
    ct_map = {}
    for r in conn.execute("SELECT id, name FROM concept_types").fetchall():
        ct_map[r['name']] = r['id']
    
    qt_map = {}
    for r in conn.execute("SELECT id, name FROM question_types").fetchall():
        qt_map[r['name']] = r['id']
    
    # 确保所有题型存在
    for qn in ["填空题", "选择题", "判断题", "简答题", "实验题", "连线题", "作图题"]:
        if qn not in qt_map:
            c = conn.execute("INSERT INTO question_types (name) VALUES (?)", (qn,))
            qt_map[qn] = c.lastrowid
    
    material_id = 4
    
    # 2. 遍历每一页
    for item in results:
        pn = item["page"]
        raw = item["content"]
        
        try:
            data = json.loads(raw)
        except:
            print(f"  P{pn}: JSON解析失败，跳过")
            continue
        
        # 获取页面ID
        sp = conn.execute(
            "SELECT id FROM source_pages WHERE material_id=? AND page_number=?",
            (material_id, pn)
        ).fetchone()
        if not sp:
            print(f"  P{pn}: 没有 source_page 记录，跳过")
            continue
        sp_id = sp['id']
        
        unit = data.get("unit", "")
        page_type = data.get("page_type", "")
        
        # 2a. 概念入库
        concepts = data.get("concepts", [])
        for c in concepts:
            if isinstance(c, dict):
                name = c.get("name", "")
                if not name:
                    continue
                definition = c.get("definition", "")
                ctype = c.get("type", "常考概念")
                cunit = c.get("unit", unit)
                
                # 去重
                existing = conn.execute(
                    "SELECT id FROM concepts WHERE name=? AND course_id=1",
                    (name,)
                ).fetchone()
                if existing:
                    continue
                
                ct_id = ct_map.get(ctype, ct_map.get("常考概念"))
                conn.execute('''INSERT INTO concepts 
                    (name, definition, concept_type_id, course_id, unit)
                    VALUES (?,?,?,?,?)''',
                    (name, definition, ct_id, 1, cunit))
                new_concepts += 1
                print(f"  P{pn}: 新概念 [{ctype}] {name}")
        
        # 2b. 题目入库
        questions = data.get("questions", [])
        for q in questions:
            if isinstance(q, dict):
                qtext = q.get("题目", "")
                if not qtext:
                    continue
                qnum = str(q.get("题号", ""))
                correct = q.get("答案", "")
                kp = q.get("知识点", "")
                qtype_name = q.get("题型", "")
                options = q.get("选项", None)
                difficulty = q.get("难度", 3)
                score = q.get("分值", 1)
                qunit = q.get("单元", unit)
                
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
                
                # 找概念ID
                concept_id = None
                if kp:
                    found = conn.execute(
                        "SELECT id FROM concepts WHERE name=? AND course_id=1",
                        (kp,)
                    ).fetchone()
                    if found:
                        concept_id = found['id']
                
                tags = json.dumps({"unit": qunit, "source": "教材"})
                
                conn.execute('''INSERT INTO raw_questions 
                    (source_page_id, material_id, course_id, question_number, question_text,
                     question_type_id, options, correct_answer, difficulty, score_value,
                     knowledge_point, concept_id, tags, raw_response_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (sp_id, material_id, 1, qnum, qtext,
                     qt_id, options, correct, difficulty, score,
                     kp, concept_id, tags, json.dumps(q, ensure_ascii=False)))
                new_questions += 1
                print(f"  P{pn}: 新题目 [{qtype_name}] 题{qnum}: {qtext[:30]}...")
        
        total_concepts += len(concepts)
        total_questions += len(questions)
    
    conn.commit()

print(f"\n{'='*50}")
print(f"教材提取总览:")
print(f"  页面中有概念: {total_concepts} 条")
print(f"  页面中有题目: {total_questions} 道")
print(f"  新入库概念: {new_concepts}")
print(f"  新入库题目: {new_questions}")

with get_conn() as c:
    qc = c.execute("SELECT COUNT(*) FROM raw_questions").fetchone()[0]
    cc = c.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    print(f"\n数据库最终状态:")
    print(f"  题目总数: {qc}")
    print(f"  概念总数: {cc}")
