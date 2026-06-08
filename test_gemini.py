# 测试 Gemini 2.5 Flash
import sys, json, urllib.request, base64, io

# key 以 base64 编码形式存储在脚本中
ENCODED_KEY = "c2stcFg5Li4uWGhmdg=="

API_KEY = base64.b64decode(ENCODED_KEY).decode()
API_URL = "https://ai-api.kkidc.com/v1/chat/completions"

import pypdfium2 as pdfium

pdf_path = r"C:\Users\HermesCC\.hermes\cache\documents\doc_5ebc6c9c7caf_科学六年级上教科版.pdf"
pdf = pdfium.PdfDocument(pdf_path)
page = pdf[0]
bitmap = page.render(scale=1.5)
img = bitmap.to_pil()
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=80)
b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
print(f"\u56fe\u7247: {len(b64)//1024}KB", flush=True)
pdf.close()

body = {
    "model": "gemini-2.5-flash",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "\u8bf7\u7528\u4e2d\u6587\u63cf\u8ff0\u8fd9\u5f20\u56fe\u7247\uff0c\u8fd9\u662f\u4ec0\u4e48\u9875\u9762\uff1f"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]
    }],
    "temperature": 0.1,
    "max_tokens": 1024
}

data = json.dumps(body).encode("utf-8")
req = urllib.request.Request(
    API_URL, data=data,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
)
with urllib.request.urlopen(req, timeout=120) as resp:
    result = json.loads(resp.read().decode("utf-8"))
    print(result["choices"][0]["message"]["content"][:600])

print("\u2713 \u6210\u529f!")
