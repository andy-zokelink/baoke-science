# MKS HTML 生成规范 — Harry科学小升初

## 数据源
**数据库**：`D:/MKS/宝科小升初/baoke_learning.db`（21张表，SQLite）
**工具**：`D:/MKS/宝科小升初/db_utils_v2.py`

```python
import sys; sys.path.insert(0, 'D:/MKS/宝科小升初')
from db_utils_v2 import *

# 核心数据
wrong = get_wrong_answers()        # 全部错题（含溯源）
all_q = get_all_questions_with_answers()  # 全量题目
stats = get_concept_type_stats()   # 概念分类统计
kp = get_kp_error_stats()          # 知识点错误分布
student = get_student()            # 学生信息
course = get_course()              # 课程信息
```

**严禁直接从 JSON 或文本文件读取，必须走数据库。**

## 用户
- Harry，六年级，深圳某小学
- 当前不及格，目标 **80分**
- 终端：平板（移动端优先）

## 5栏目规范
1. **知识概览**：概念体系 + ★★★核心/★★常考/★易错/·边缘 标注 + 学习路径
2. **知识卡片**：3D翻转，正面概念名+标签，反面定义+关联错题
3. **练习题**：40-50道，重点倾斜易错概念
4. **错题本**：历史错题 + 错误原因 + 正确思路 + 出题规律 + 溯源信息
5. **思维导图**：Graphviz SVG，≥3层，4色区分概念类型

禁止：苏格拉底追问、案例分析

## 设计
- 暖色系 #fdf6ec/#fffaf2/#c0392b/#3d2f2f
- 3D翻转卡片 clamp() 响应式
- MCQ 选项均匀分布
- localStorage 持久化
- 移动端 375px 全功能

## 自检 + 验收
1. node 语法无错
2. 5栏目齐全，无苏格拉底/案例
3. 概念标注 4 级分类
4. SVG ≥3层+4色+图例
5. 错题含溯源信息
6. 数据来自数据库验证
