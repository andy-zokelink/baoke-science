"""
批量处理教材剩余页面（第18-40页）
从 Hermes config 的 auxiliary.vision 读取完整 API key
"""
import json, base64, os, time, sqlite3, re, urllib.request, sys, yaml

# === 从 Hermes config 读 key ===
hermes_cfg = os.path.expanduser("~/.hermes/config.yaml")
with open(hermes_cfg) as f:
    cfg = yaml.safe_load(f)
av = cfg.get("auxiliary", {}).get("vision", {})
API_KEY = av.get("api_key", "")
API_URL = av.get("base_url", "https://ai-api.kkidc.com/v1") + "/chat/completions"

print(f"Key: {len(API_KEY)}ch, prefix={API_KEY[:12]}...")

# === 路径 ===
DB = r"C:\Users\HermesCC\baoke-science\baoke_learning.db"
OUT = r"C:\Users\HermesCC\baoke-science\textbook_extracted"
IMG = os.path.join(OUT, "images")
os.makedirs(OUT, exist_ok=True)
MATERIAL_ID = 4

# === 数据库 ===
def get_conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def save_page(mid, pn, text):
    with get_conn() as c:
        e = c.execute("SELECT id FROM source_pages WHERE material_id=? AND page_number=?", (mid, pn)).fetchone()
        if e:
            c.execute("UPDATE source_pages SET ocr_text=?,processed_at=CURRENT_TIMESTAMP WHERE material_id=? AND page_number=?", (text,mid,pn))
            return e['id']
        return c.execute("INSERT INTO source_pages (material_id,page_number,ocr_text,ocr_method,processed_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)", (mid,pn,text,'gemini_vision')).lastrowid

# === Gemini 调用 ===
PROMPT = """你是中国小学科学教育专家。分析这张教科版六年级上册科学教材的页面，输出JSON。

{ "page_type": "封面|目录|单元首页|正文|练习|活动|版权页|空白页",
  "unit": "单元名称",
  "content_summary": "一句话概述",
  "concepts": [
    { "name": "概念名称", "definition": "精确定义30字内", "type": "核心概念|常考概念|易错概念", "unit": "所属单元" }
  ],
  "questions": [
    { "题号": "1", "题型": "填空题|选择题|判断题|简答题|实验题|连线题", "题目": "完整题目文本", "选项": ["A.xxx","B.xxx"], "答案": "正确答案", "知识点": "知识点名", "难度": 3, "单元": "所属单元", "分值": 1 }
  ],
  "key_knowledge": "本页最重要的知识点总结"
}

注意：练习题每个小题单独列出；图片用【图:描述】注明；直接输出纯JSON不用```包裹；无概念则concepts留空；无题目则questions留空"""

def call_gemini(image_path, retries=3):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    body = {
        "model": "gemini-2.5-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
        }],
        "temperature": 0.1,
        "max_tokens": 8192
    }
    data = json.dumps(body).encode("utf-8")
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API_URL, data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  Retry {attempt+1}/{retries}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    raise Exception("All retries failed")

# === 分批处理 ===
# 找出待处理页面
done = set()
for pn in range(1, 41):
    p = os.path.join(OUT, f"page_{pn:03d}.json")
    if os.path.exists(p) and os.path.getsize(p) > 100:
        done.add(pn)

pending = sorted(set(range(1, 41)) - done)
print(f"已处理: {len(done)} 页")
print(f"待处理: {len(pending)} 页: {pending}")
print("=" * 50, flush=True)

tq, tc, tok, tfail = 0, 0, 0, 0

for idx, pn in enumerate(pending):
    img_path = os.path.join(IMG, f"page_{pn:03d}.jpg")
    json_path = os.path.join(OUT, f"page_{pn:03d}.json")
    
    print(f"\n[{idx+1}/{len(pending)}] P{pn}/40", flush=True)
    
    try:
        raw = call_gemini(img_path)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n```$', '', raw)
        
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(raw)
        save_page(MATERIAL_ID, pn, raw)
        tok += 1
    except Exception as e:
        print(f"  FAIL: {e}", flush=True)
        tfail += 1
        err = json.dumps({"page_type": "error", "error": str(e), "page": pn})
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(err)
        continue
    
    try:
        d = json.loads(raw)
        nq = len(d.get("questions", []))
        nc = len(d.get("concepts", []))
        tq += nq
        tc += nc
        print(f"  {d.get('page_type','?')} | {str(d.get('unit',''))[:15]} | C:{nc} Q:{nq}")
    except:
        print(f"  saved, len={len(raw)}")
    
    time.sleep(1.5)

print("\n" + "=" * 50, flush=True)
print(f"完成! OK:{tok} Fail:{tfail} | 新增概念:{tc} 新增题目:{tq}", flush=True)

# === 统计汇总 ===
print("\n全量表统计:", flush=True)
with get_conn() as c:
    qc = c.execute("SELECT COUNT(*) FROM raw_questions").fetchone()[0]
    cc = c.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    sp = c.execute("SELECT COUNT(*) FROM source_pages WHERE material_id=?", (MATERIAL_ID,)).fetchone()[0]
    print(f"  题目: {qc}")
    print(f"  概念: {cc}")
    print(f"  页面: {sp}")
