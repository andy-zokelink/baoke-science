# 宝科小升初 — Harry学习追踪系统

## 数据库
- **路径**：`baoke_learning.db`（21表，SQLite，自动解析相对路径）
- **工具**：`db_utils_v2.py`
- **架构**：7层（字典→素材溯源→题目→概念→追踪→媒体→日志）

## 当前状态
```python
from db_utils_v2 import *
get_student()   # {'name': 'Harry', 'school': '深圳某小学'}
get_course()    # {'subject': '科学', 'grade': '六年级', 'target_score': 80.0}
get_question_count()  # 688
get_wrong_count()     # 183
```
· 433✓ / 183✗ / 2半对 / 31未答
· 99概念全部已填定义（核心6/常考84/易错5/边缘4）
· 题型：填空337 / 简答335 / 判断11 / 选择5

## 再生脚本
- `regenerate_wrongbook.py` — 从DB重新生成错题本HTML section
- `update_html_concepts.py` — 从DB重新生成CONCEPTS数据
- `update_definitions.py` — 从JSON更新DB概念定义

## 部署
- **GitHub Pages**: https://andy-zokelink.github.io/baoke-science/
- 从 `/docs` 目录自动构建

## MKS 生成规范
见 `mks-builder.md`

## 开发
```bash
python regenerate_wrongbook.py   # DB → HTML 错题本
python update_html_concepts.py   # DB → HTML CONCEPTS
python update_definitions.py     # JSON → DB 概念定义
```
