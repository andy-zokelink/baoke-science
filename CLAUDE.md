# 宝科小升初 — Harry学习追踪系统

## 数据库
- **路径**：`/Users/andy/MKS/宝科小升初/baoke_learning.db`（21表，SQLite）
- **工具**：`/Users/andy/MKS/宝科小升初/db_utils_v2.py`
- **架构**：7层（字典→素材溯源→题目→概念→追踪→媒体→日志）

## 当前状态
```python
from db_utils_v2 import *
get_student()   # {'name': 'Harry', 'school': '深圳某小学'}
get_course()    # {'subject': '科学', 'grade': '六年级', 'target_score': 80.0}
get_question_count()  # 78
get_wrong_count()     # 15
```

## MKS 生成规范
见 `~/.claude/skills/mks-builder.md`

## 部署
- **生产环境**: https://baoke-science.pages.dev
- **最新部署**: https://8d2f1aa7.baoke-science.pages.dev
```bash
cd /Users/andy/MKS/宝科小升初
wrangler pages deploy pages/ --project-name=baoke-science --branch=main
```
