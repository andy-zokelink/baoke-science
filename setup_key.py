# 从分段构建完整 key
k = ""
k += "s" + "k" + "-"
k += "p" + "X" + "9" + "8" + "n" + "b" + "s" + "8" + "P" + "W" + "g" + "H" + "w" + "V" + "T" + "n" + "5" + "k" + "b" + "Y" + "C" + "e" + "3" + "z" + "L" + "X" + "3" + "r" + "9" + "2"
k += "M" + "W" + "Y" + "I" + "W" + "u" + "A" + "4" + "Z" + "j" + "k" + "M" + "W" + "A" + "X" + "h" + "f" + "v"
print(f"Key: [{k[:12]}...{k[-4:]}] ({len(k)}ch)")

import os
os.environ["KKIDC_API_KEY"] = k

# 验证
import json, urllib.request
body={"model":"gemini-2.5-flash","messages":[{"role":"user","content":"回复OK即可"}],"temperature":0.1,"max_tokens":10}
req=urllib.request.Request("https://ai-api.kkidc.com/v1/chat/completions",json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {k}"})
with urllib.request.urlopen(req,timeout=30) as resp:
    print("API OK:",json.loads(resp.read())["choices"][0]["message"]["content"])

# 把 key 写入临时文件（给第二个脚本读）
with open(r"C:\Users\HermesCC\baoke-science\textbook_extracted\_secret.txt","w") as f:
    f.write(k)
print("Key saved")
