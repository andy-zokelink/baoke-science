import os, sys, json, time, sqlite3, base64, re, urllib.request
from pathlib import Path

# 从 _secret.txt 读取 API KEY（setup_key.py 已写入完整 key）
_secret_path = r"C:\Users\HermesCC\baoke-science\textbook_extracted\_secret.txt"
if os.path.exists(_secret_path):
    with open(_secret_path) as f:
        API_KEY = f.read().strip()
elif os.environ.get("KKIDC_API_KEY"):
    API_KEY=os.env...t(1)

API_URL = "https://ai-api.kkidc.com/v1/chat/completions"

DB_PATH = r"C:\Users\HermesCC\baoke-science\baoke_learning.db"
OUTPUT_DIR = r"C:\Users\HermesCC\baoke-science\textbook_extracted"
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")
MATERIAL_ID = 4

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def save_page(mid, pn, text):
    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM source_pages WHERE material_id=? AND page_number=?", (mid,pn)).fetchone()
        if ex:
            conn.execute("UPDATE source_pages SET ocr_text=?,processed_at=CURRENT_TIMESTAMP WHERE material_id=? AND page_number=?", (text,mid,pn))
            return ex['id']
        c = conn.execute("INSERT INTO source_pages (material_id,page_number,ocr_text,ocr_method,processed_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)", (mid,pn,text,'gemini_vision'))
        return c.lastrowid

PROMPT = """你是中国小学科学教育专家。分析这张教科版六年级上册科学教材的页面，输出JSON。

{ "page_type": "封面|目录|单元首页|正文|练习|活动|版权页|空白页",
  "unit": "单元名称",
  "content_summary": "一句话概述",
  "concepts": [{ "name": "概念名", "definition": "精确定义30字内", "type": "核心概念|常考概念|易错概念", "unit": "所属单元" }],
  "questions": [{ "题号": "1", "题型": "填空题|选择题|判断题|简答题|实验题|连线题", "题目": "完整题目", "选项": ["A.xx","B.xx"], "答案": "正确答案", "知识点": "知识点名", "难度": 3, "单元": "所属单元", "分值": 1 }],
  "key_knowledge": "本页最重要知识点"
}
注意：每个小题单独列出；图片用【图:描述】注明；直接输出JSON不要用```；无概念concepts留空；无题目questions留空"""

def call_gemini(image_path, retries=3):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    body = {"model":"gemini-2.5-flash","messages":[{"role":"user","content":[{"type":"text","text":PROMPT},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]}],"temperature":0.1,"max_tokens":8192}
    data = json.dumps(body).encode("utf-8")
    for a in range(retries):
        try:
            req = urllib.request.Request(API_URL,data,headers={"Content-Type":"application/json","Authorization":f"Bearer {API_KEY}"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  R{a+1}: {e}", flush=True)
            time.sleep(3*(a+1))
    raise Exception("Failed")

# 确定待处理页面
all_pages = set(range(1, 41))
done = set()
for pn in range(1, 41):
    jp = os.path.join(OUTPUT_DIR, f"page_{pn:03d}.json")
    if os.path.exists(jp) and os.path.getsize(jp) > 100:
        done.add(pn)

pending = sorted(all_pages - done)
print(f"已处理: {len(done)} 页")
print(f"待处理: {len(pending)} 页: {pending}")
print("=" * 50, flush=True)

tq, tc, tok, tfail = 0, 0, 0, 0
for pn in pending:
    img = os.path.join(IMAGE_DIR, f"page_{pn:03d}.jpg")
    jp = os.path.join(OUTPUT_DIR, f"page_{pn:03d}.json")
    print(f"\nP{pn}/40", flush=True)
    
    try:
        raw = call_gemini(img)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?','',raw)
            raw = re.sub(r'\n```$','',raw)
        with open(jp,"w",encoding="utf-8") as f:
            f.write(raw)
        save_page(MATERIAL_ID, pn, raw)
        tok += 1
    except Exception as e:
        print(f"  FAIL: {e}", flush=True)
        tfail += 1
        err = json.dumps({"page_type":"error","error":str(e),"page":pn})
        with open(jp,"w",encoding="utf-8") as f:
            f.write(err)
        continue
    
    try:
        d = json.loads(raw)
        nq = len(d.get("questions",[]))
        nc = len(d.get("concepts",[]))
        tq += nq; tc += nc
        print(f"  {d.get('page_type','?')} | {str(d.get('unit',''))[:15]} | C:{nc} Q:{nq}")
    except:
        print(f"  saved, len={len(raw)}")
    
    time.sleep(1.5)

print("\n" + "=" * 50, flush=True)
print(f"完成! OK:{tok} Fail:{tfail} | 新增概念:{tc} 新增题目:{tq}", flush=True)
print(f"当前累计: 概念{tc}个 题目{tq}个", flush=True)
