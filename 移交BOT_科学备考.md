# 科学备考项目 — 移交 BOT 包

## 👤 目标用户
- **Harry**，六年级，深圳某小学
- 当前不及格 → 目标 80 分
- 终端：平板（移动端优先）

## 📊 数据库概况
- `baoke_learning.db`（SQLite，19张活跃表）
- 688 道题（433对 / 183错 / 72未答）
- 99 个概念，全部已填写定义（4级分类）
- 学生信息已脱敏

## 📁 文件清单

| 文件 | 用途 |
|------|------|
| `baoke_learning.db` | SQLite 数据库（所有题目+概念+追踪数据） |
| `db_utils_v2.py` | 数据库读写工具包（DB路径已改为动态路径） |
| `docs/index.html` | 最终交付物（5栏目交互页面） |
| `concept_defs.json` | 概念定义补充数据（JSON格式） |
| `CLAUDE.md` | Claude Code 项目上下文 |
| `mks-builder.md` | MKS 构建 skill 规范 |
| `claude_settings.json` | Claude Code 配置参考 |
| `update_definitions.py` | 从 JSON 更新数据库概念定义 |
| `update_html_concepts.py` | 从数据库重新生成 HTML 中 CONCEPTS 数据 |
| `fill_definitions.py` | 概念定义文件（原始版本） |
| `移交文档_阿爪.md` | 原始移交文档 |

## 🔧 数据库读取

```python
import sys; sys.path.insert(0, '/Users/andy/MKS/宝科小升初')
from db_utils_v2 import *

# 核心数据
wrong = get_wrong_answers()                # 全部错题（含溯源）
all_q = get_all_questions_with_answers()   # 全量题目
stats = get_concept_type_stats()           # 概念分类统计
kp = get_kp_error_stats()                  # 知识点错误分布
student = get_student()                    # 学生信息
course = get_course()                      # 课程信息
```

其他可用函数：`get_question_count()`, `get_wrong_count()`, `insert_question()`, `record_answer()`, `add_concept()`, `register_source_material()`

## 🏗 构建流程

```
PDF(图片版) → Gemini Vision 逐页识别 → raw_questions 入库
→ DeepSeek 知识点归纳(纯文本) → concepts 概念组入库
→ Claude Code 读库生成 HTML → 复核 → 浏览器测试
```

## 📦 当前版本功能（5栏目）

1. **知识概览** — 99概念按4级分类（★★★核心/★★常考/★易错/·边缘），5大领域折叠
2. **知识卡片** — 99张3D翻转卡，正面概念名+标签，反面定义+陷阱
3. **模拟考试** — 从MCQ题池随机抽30道选择题，15分钟倒计时
4. **错题本** — 历史错题 + TOP12高频错误 + 出题规律 + 溯源
5. **思维导图** — 内联SVG，4层径向布局

## ✅ 阿爪已完成

- macOS 路径适配（Windows → Mac）
- 正确率动态计算（原硬编码63% → 从数据计算70%）
- submitExam 死代码清理（判断题/填空题不可达分支已移除）
- 78个空概念定义全部补充（含常见陷阱提示）
- 隐私脱敏（姓名/学校/班级全部替换）
- GitHub Pages 部署：https://andy-zokelink.github.io/baoke-science/

## ⚠️ 待完成

1. **出卷功能** — 用户自定义题型/数量，生成标准试卷，导出PDF/Word
2. **HTML 里 CONCEPTS 的 domain 字段** — 我补充概念定义时添加了 domain 推断，但可能不够准确，建议从 DB 重新校准
3. **错题本 80 vs 183** — header 显示 183 错题，错题本显示 80，需确认是展示子集还是 bug
4. **更多题库** — 688 题中选择题仅 5 道，模拟考试依赖 MCQ 化转换，可考虑扩充原生选择题

## 🚀 如何继续

```bash
cd /Users/andy/MKS/宝科小升初

# Claude Code 模式
claude -p "你的任务" --effort xhigh --max-turns 80

# 直接操作数据库
python3 -c "
from db_utils_v2 import *
print(get_wrong_answers()[0])
"

# 浏览器测试
open docs/index.html

# 部署到 GitHub Pages
git add -A && git commit -m 'msg' && git push
# Pages 自动从 /docs 构建
```

## 🔗 线上地址

- GitHub 仓库：https://github.com/andy-zokelink/baoke-science
- GitHub Pages：https://andy-zokelink.github.io/baoke-science/
