# 宝科科学备考 — Claude Code 重建指令

## 你的目标
从 baoke_learning.db 读取全量数据，重建 docs/index.html，6个栏目全功能网站。

## 第一步：读数据摸底
```bash
cd C:\Users\HermesCC\baoke-science
python -c "from db_utils_v2 import *; import json; print(f'题目:{get_question_count()} 错题:{get_wrong_count()}')"
python -c "from db_utils_v2 import *; [print(q['question_text'][:30], q.get('knowledge_point',''), q.get('is_correct','')) for q in get_all_questions_with_answers()[:3]]"
```

## 第二步：从 SQLite 生成全量 data.js（索引.html用）
用命令 python -c "..." 提取全部数据，生成一个 data.js 文件。结构：
- questions: raw_questions + student_answers 关联
- concepts: concepts + concept_types + concept_relations
- source_pages: 教材溯源

## 第三部：重建 docs/index.html（6栏）

1. **冲刺主页** — 仪表盘：正确率、薄弱知识点TOP5、倒计时、进度条
2. **知识地图** — 182概念按领域/单元折叠，4级分类（★★★核心/★★常考/★易错/·边缘）
3. **错题诊所** — 按知识点聚类错题，高频错误TOP、出题陷阱归纳
4. **知识图谱** — SVG 呈现概念间关系（依赖/包含/因果），可用 NetworkX 预计算布局
5. **冲刺计划** — 按错误频次+距离考试天数，动态生成复习清单
6. **教材溯源** — 按教材页码浏览，展示教科书中提取的题目和知识点

## 风格
- 移动端优先（平板+手机）
- 深色/浅色主题切换
- 配色淡蓝+白色，清爽学习风格
- CSS 动画：卡片翻转、加载过渡

## 约束
- 纯静态 HTML/CSS/JS，不依赖外部 npm/CDN
- 所有数据从 data.js 读取，不硬编码
- 不要 rush — 每完成一个栏目自测
- 最终打开 docs/index.html 浏览器测试
- 测试通过后，运行：git add -A && git commit -m "全量重建：799题+182概念+教材溯源" && git push
