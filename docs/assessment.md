# 宝科科学备考项目 — 完整评估报告

> 生成日期：2026-06-09
> 项目路径：`C:\Users\HermesCC\baoke-science\`
> 数据库：`baoke_learning.db` (SQLite, 21表)

---

## 一、概念网络问题根因分析 (Tab 3 空的)

### 1.1 数据流现状

```
analyze_concepts.py → concept_relations.json (565 edges, 182 nodes)
                                          ↓
export_data.py → docs/data.js (BAOKE_DATA.relations 字段, 565条)
                                          ↓
docs/index.html (buildGraphData函数读取 BAOKE_DATA.relations)
```

### 1.2 结论：数据流本身没有问题

经过逐层验证：

| 层次 | 状态 | 校验结果 |
|------|------|----------|
| `concept_relations.json` | ✅ 正常 | 565 edges, 182 nodes, source/target用概念名称 |
| `data.js` 中 `relations` 字段 | ✅ 正常 | 导出565条关系，top-level字段 |
| 概念名称匹配 | ✅ 完全匹配 | 169个关系中的唯一名称全部与概念名匹配 |
| `buildGraphData` 函数 | ✅ 逻辑正确 | line 572: `if(BAOKE_DATA.relations && BAOKE_DATA.relations.length)` |

### 1.3 可能的真正原因

1. **DB `concept_relations` 表为空**（0行）。`analyze_concepts.py` 只写 JSON 不写 DB。虽然 `export_data.py` 已回退到读 JSON（line 44-56），但如果之前部署时 `data.js` 是从 DB 生成的旧版本，则 `relations` 字段可能为空。
2. **Tab 3 需要手动切换到该标签才触发 `runGraph()`**（line 395），如果用户切换后没有等 `setTimeout(runGraph,100)` 执行，或 SVG 渲染时还没拿到 `graphWrap` 容器的 `clientWidth`，可能渲染为空。
3. **`graphWrap` CSS 的 `min-height` 在移动端可能不够**，导致 SVG 不可见。

### 1.4 修复建议

1. 重新运行 `python export_data.py` 重新生成 `data.js`（确保包含565条关系）
2. 在 `buildGraphData` 顶部加 `console.log('Graph data:', BAOKE_DATA.relations?.length, 'relations,', _C.length, 'concepts')`
3. 在 `runGraph()` 中加容错处理：若 `graphWrap.clientWidth === 0` 则设默认值
4. 推荐方案：将 `export_data.py` 改为输出时也写入 `concept_relations` 表，双保险

---

## 二、题型分布统计

### 2.1 全库题型分布

| 题型 | 数量 | 占比 | 其中错题 |
|------|------|------|----------|
| 填空题 | 339 | 42.4% | 70 |
| 简答题 | 436 | 54.6% | 109 |
| 判断题 | 17 | 2.1% | 2 |
| 选择题 | 7 | 0.9% | 2 |
| **总计** | **799** | **100%** | **183** |

### 2.2 选项数据情况

| 题型 | 有options | 无options | 有correct_answer |
|------|-----------|-----------|-----------------|
| 选择题 (7) | 7 | 0 | 7 |
| 判断题 (17) | 6 | 11 | 5 |
| 填空题 (339) | 2 | 337 | 0 |
| 简答题 (436) | 24 | 412 | 99 |

### 2.3 非选择题转选择题可行性评估

**数据现状**：
- 34道题有 `options` 字段，但其中大部分是空数组 `[]`
- 仅有 **111道题** 有 `correct_answer`（主要为简答题，答案=文字描述）
- 大部分填空题连 `correct_answer` 都没有
- `raw_response_json` 中的 `选项` 字段也基本为空（仅判断题有 `['正确','错误']` 或 `['对','错']`）

**可行方案**：

**方案A：自动生成选项（更可行）**
- 对每道非选择题，用正确答案 + 从同知识点其他题目提取的常见错误/干扰项，自动构造4个选项
- 需要：新增一个 `generate_choice_options.py` 脚本，在导出时预处理
- 优势：无需改数据库，纯脚本生成，可离线运行
- 劣势：生成的选项质量取决于题库丰富度

**方案B：新增选择题版题库**
- 在 DB 中新增 `choice_questions` 表，为每道非选择题人工或AI生成选择题版本
- 优势：质量可控
- 劣势：工作量大（436+339≈775道题需要改造）

**建议**：先实施方案A，观察效果后再决定是否细调。预计开发量：3-5天。

---

## 三、在线测试改试卷模式的方案和估算

### 3.1 当前架构分析

在线测试代码约 **200行**（line 788-1008），分为：

| 函数 | 行号 | 功能 | 行数 |
|------|------|------|------|
| `startOnlineTest` | 790 | 初始化模态框 | 10 |
| `selectTestMode` | 804 | 模式选择(3种) | 7 |
| `selectQty` | 811 | 题目数量选择 | 6 |
| `buildKpSelector` | 817 | 知识点选择器 | 12 |
| `beginTest` | 840 | 开始测试(抽题) | 38 |
| `showQuestion` | 879 | 显示单题 | 38 |
| `submitOnlineAnswer` | 918 | 选择题作答 | 24 |
| `showAnswerForQuestion` | 942 | 非选择题自评 | 12 |
| `showTestFeedback` | 954 | 反馈显示 | 11 |
| `nextOnlineQuestion` | 969 | 下一题 | 6 |
| `showResult` | 975 | 结果显示 | 28 |

### 3.2 改为"试卷模式"的改动量

**核心改动**：从"逐一展示"改为"一次全部展示"

**需要新增/重写的函数**：

| 改动项 | 类型 | 估算行数 |
|--------|------|----------|
| `renderExamPaper()` — 渲染试卷页面(全部题目) | 新增 | ~60行 |
| `submitExam()` — 一次性提交批改 | 新增 | ~40行 |
| `showExamResult()` — 成绩总览 | 新增/改造 | ~30行 |
| 改造 `beginTest()` — 生成题组+分组逻辑 | 重写 | ~25行 |
| 知识点分组渲染（按concept/knowledge_point分组） | 新增 | ~30行 |
| 改造 `testOverlay` HTML模板 | 改造 | ~30行 |
| **小计** | | **~215行** |

### 3.3 具体方案

1. **模式选择不变**（易错题专练/知识点专练/模拟测试）
2. **点击"开始测试"后**，直接渲染全部题目列表（不再进入单题模式）
   - 题目按知识点分组排列，每组有标题
   - 每道题显示完整题干 + 作答区（选择题显示选项按钮，非选择题显示文本框/自评按钮）
3. **页面底部有"提交批改"按钮**
   - 用户全部答完后点击提交
   - 一次性批改所有题目
   - 显示成绩总览（正确/错误分布、知识点薄弱项）
4. **结果页**中错的题目高亮标注正确答案，并保留错误归因/策略

### 3.4 兼容性注意

- 当前选择题只有7道——试卷模式中大部分题需要"自评按钮"（点击"我答对了/我答错了"）
- 建议：在试卷模式下，对非选择题提供**文本输入框** + **参考答案折叠**，用户先作答再对照自评

### 3.5 估算总工时

**纯前端修改**：约 4-6 小时（1人日）
- HTML 模板调整：0.5h
- 试卷渲染函数：1.5h
- 提交批改逻辑：1h
- 结果展示：1h
- 调试/联调：1-2h

---

## 四、数据联动（测试结果存库）方案对比

### 4.1 现状

- 总览页面（Tab 0）从 `data.js` 读取静态数据
- 在线测试结果仅存在于内存中，刷新后丢失
- `student_answers` 表已有 649 条记录（来自原始数据导入），但没有新增记录入口

### 4.2 方案对比

| 特性 | 方案A: localStorage | 方案B: Python后端(Flask) |
|------|--------------------|------------------------|
| 架构 | 纯前端 | 需要部署后端服务 |
| Cloudflare部署 | ✅ 直接支持 | ❌ 不支持（CP只支持静态） |
| 数据持久化 | ✅ 浏览器本地 | ✅ 服务端DB |
| 多设备同步 | ❌ 局限于单台设备 | ✅ 可同步 |
| 与现有DB整合 | ❌ 需手动导入 | ✅ 直接对接 |
| 开发量 | 2-3小时 | 8-12小时 |
| 复杂性 | 低 | 中（认证、部署、运维） |
| 建议 | ⭐ **推荐** | 作为未来升级选项 |

### 4.3 方案A 详细设计

1. **存储结构**（localStorage key: `baoke-test-results`）：
```json
[
  {
    "date": "2026-06-09T10:30:00",
    "mode": "easy",
    "total": 10,
    "correct": 7,
    "answers": [
      {"qid": 1, "correct": true},
      {"qid": 2, "correct": false}
    ],
    "timeSpent": 185
  }
]
```

2. **总览页面改造**：
   - 从 localStorage 读取最近 N 次测试结果
   - 与 `data.js` 中的错误率结合，计算综合统计数据
   - 显示"最近7天正确率趋势图"

3. **测试完成后自动保存**：
   - 在 `showResult()` 函数末尾调用 `saveTestResult()`
   - 保存到 localStorage

4. **估算开发量**：2-3小时

---

## 五、错题导出Word的纯前端方案

### 5.1 现状
当前 `exportWrongPrint()`（line 500-551）使用 `window.print()` 打印预览，浏览器可"另存为PDF"但不支持直接生成 .docx。

### 5.2 方案A: HTML → .doc (推荐)

**原理**：Word 可以直接打开 HTML 文件（使用 Word HTML 格式）。

**实施**：
1. 复用现有 `exportWrongPrint()` 的 HTML 模板结构
2. 添加 Word 兼容的 `<meta>` 和 `<style>` 声明
3. 使用 `Blob` 生成 .doc 文件并触发下载

```javascript
function exportWrongWord() {
  const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office' 
                      xmlns:w='urn:schemas-microsoft-com:office:word' 
                      xmlns='http://www.w3.org/TR/REC-html40'>
    <head><meta charset='utf-8'><title>宝科科学错题报告</title>
    <style>/* 已有样式 */</style></head>
    <body>${content}</body></html>`;
  const blob = new Blob(['\ufeff' + html], {type: 'application/msword'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = '宝科科学错题报告.doc';
  a.click(); URL.revokeObjectURL(url);
}
```

### 5.3 方案B: 使用 docx.js 库生成 .docx

**原理**：用 https://docx.js.org/ 生成真正的 .docx 格式。

**优势**：真正的 Word XML 格式，样式精确
**劣势**：需要额外引入一个库（CDN加载约100KB）
**估算**：开发量相当于方案A的2倍

### 5.4 建议
先用**方案A**（HTML→.doc），10分钟实现，大部分Word都能打开。如果用户需要更精确的排版再升级到方案B。

---

## 六、概念故事化展示的设计思路

### 6.1 需求解读
Tab 1（知识图谱）从"4级分类折叠列表"改为"按科学领域分章节展示概念间的逻辑关系，类似教科书单元→课节→概念结构"。

### 6.2 当前数据可支持性

| 所需字段 | 数据状态 |
|----------|----------|
| 领域（科学领域） | ✅ 概念在 `concept_relations.json` 中有 `domain` 字段（5个领域） |
| 单元（教科书单元） | ⚠️ 仅 83 个概念有 `unit` 值，其余99个为 NULL |
| 课节/章节 | ❌ 无此字段 |
| 概念间关系 | ✅ 565条关系（依赖/包含/并列） |

### 6.3 设计思路

**方案：基于 domain 的卡片流展示**

```
┌──────────────────────────────────────────────┐
│ 🔬 科学领域                                  │
│ [物质科学] [生命科学] [地球宇宙] [技术工程]   │  ← 领域Tab切换
├──────────────────────────────────────────────┤
│                                              │
│  🧪 物质科学 (61个概念)                      │
│                                              │
│  🌊 === 水的三态变化 ===                     │  ← 概念群组(自动聚类)
│  │  [水] ──→ [水蒸气] ──→ [冰]              │  ← 关系箭头
│  │  [蒸发] ──→ [凝结]                       │
│  ├── 概念卡片(点击展开定义+错题链接)         │
│  │                                          │
│  ⚡ === 能量转换 ===                         │
│  │  [电能] ═══ [热能] ═══ [光能]            │
│  │  [机械能] ──→ [动能]                     │
│  │                                          │
├──────────────────────────────────────────────┤
│  📚 关联错题: 12道  |  掌握率: 68%           │
└──────────────────────────────────────────────┘
```

### 6.4 实现步骤

1. **数据预处理**：在 `export_data.py` 或新增脚本中，根据 `domain` 和 `relations` 自动计算概念分组
2. **前端组件**：
   - 领域切换 Tab（物质科学/生命科学/地球宇宙/技术工程/其他）
   - 每个领域内按 concepts 自动分组（基于 relation 密度聚类）
   - 每组用卡片流/时间线布局展示概念和关系
   - 点击概念展开定义、错题数、链接到错题诊疗
3. **复用 Tab 3 的关系数据**：直接从 `BAOKE_DATA.relations` 和 `BAOKE_DATA.concepts` 渲染

### 6.5 估算
**开发量**：4-6小时（纯前端）
- 数据预处理聚类逻辑：1h
- 领域切换+卡片流UI：2h
- 概念卡片交互（展开/跳转）：1h
- 链接到错题：0.5h
- 调试：1-1.5h

---

## 七、其余需求快速评估

### 7.1 学习计划改为清单模式 (Tab 4)

**当前**：7天排期，每天分若干项
**需求**：TODO list 清单，按优先级排列，可勾选

**改动量估算**：2-3小时
- `generatePlan()` 函数只需修改约30行（去掉7天循环，改为扁平列表）
- `togglePlanItem()` / `togglePlanDay()` 可复用
- localStorage 持久化逻辑不变

### 7.2 错题诊疗改为选择题形式 (Tab 2)

**当前**：`showQuestion()` 对非选择题显示"自评按钮"
**需求**：自动加4个选项

**核心问题**：没有现成的选项数据。**必须先完成"非选择题转选择题"（第二章方案A），然后才能改在线测试。**

**依赖链**：数据预处理(方案A) → 选项字段注入 → showQuestion改造

### 7.3 整体排版优化

**当前问题**：1040行单文件，CSS和JS混合，移动端显示待优化

**建议**：
1. 将大段 CSS 抽到独立 `<style>` 区域（已基本做到）
2. 统一间距：当前使用 `gap:12px`、`padding:16px` 基本一致，但不同卡片间距不统一
3. 移动端：`max-width:480px` 的媒体查询只有13行，需要补充更多断点
4. 代码组织：JS部分按Tab分块（已做到），但可以进一步抽取为独立函数文件

**估算**：3-5小时

---

## 八、总体改动量估算汇总

| 序号 | 需求模块 | 优先级 | 改动类型 | 估算工时 | 前置依赖 |
|------|---------|--------|----------|----------|----------|
| 1 | 概念网络Debug修复 | 🔴 紧急 | 补console.log + 容错 | 0.5h | 无 |
| 2 | 非选择题转选择题 | 🔴 高 | 新增脚本预处理 | 3-5天 | 无 |
| 3 | 在线测试改试卷模式 | 🔴 高 | 重写200行JS | 4-6h | 无(但选项丰富依赖#2) |
| 4 | 总览D-A联动(localStorage) | 🟡 中 | 新增30行JS | 2-3h | 无 |
| 5 | 学习计划改清单 | 🟡 中 | 改造30行JS | 2-3h | 无 |
| 6 | 概念故事化展示 | 🟡 中 | 新增200行JS+HTML | 4-6h | 无 |
| 7 | 错题导出Word | 🟢 低 | 新增20行JS | 0.5h | 无 |
| 8 | 整体排版优化 | 🟢 低 | CSS整理 | 3-5h | 无 |
| | **总计（核心改动 1-3）** | | | **3-6人天** | |
| | **总计（含全部 1-8）** | | | **5-9人天** | |

### 8.1 建议执行顺序

```
第1天：修复概念网络(#1) + 选择题选项生成脚本(#2的前端预处理部分)
第2天：在线测试改试卷模式(#3)
第3天：总览D-A联动(#4) + 学习计划改清单(#5)
第4天：概念故事化展示(#6)
第5天：排版优化(#8) + 错题导出Word(#7)
```

---

## 附录A：关键文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| 前端主页面 | `docs/index.html` | 1040行，6个Tab + 在线测试弹窗 |
| 全量数据 | `docs/data.js` | 约2MB，~32,000行JSON |
| 数据库 | `baoke_learning.db` | SQLite，21表，799题 |
| 数据导出 | `export_data.py` | DB → data.js 导出脚本 |
| 概念关系生成 | `analyze_concepts.py` | concepts → concept_relations.json |
| 概念关系JSON | `concept_relations.json` | 565 edges, 182 nodes |
| DB工具 | `db_utils_v2.py` | 数据库查询工具 |
| 错题再生 | `regenerate_wrongbook.py` | 错题本HTML生成 |
| HTML概念更新 | `update_html_concepts.py` | 概念数据更新 |
| 定义更新 | `update_definitions.py` | JSON → DB 定义同步 |

## 附录B：数据库 student_answers 表

已有 **649条**记录（183条错题）。表结构支持：
- `question_id`, `student_id`, `student_response`, `is_correct`
- `error_cause`, `error_detail`, `exam_strategy`
- `exam_session_id`（可关联到考试会话）
- `answer_date`, `created_at`

此表可作为"测试结果存库"的直接目标表。

## 附录C：概念网络数据验证详情

```
concept_relations.json: 565 edges, 182 nodes
  - 关系类型: 并列(419) 依赖(121) 包含(25)
  - 领域分布: 物质科学(61) 生命科学(37) 地球宇宙(37) 技术工程(33) 其他(14)
  - 孤立节点: 无（全部182节点均有至少1条边）
  
DB concept_relations 表: 0行 （问题线索！）
  - analyze_concepts.py 只写JSON不写DB
  - export_data.py 已做回退：优先读JSON，JSON不存在再读DB
  
data.js BAOKE_DATA.relations: 565条（与JSON一致）
  - 概念名称匹配: 169/169 完全匹配
  
buildGraphData() 逻辑:
  - line 571: 用 _C (concepts数组) 构建 nameToId 映射
  - line 572: 检查 BAOKE_DATA.relations 是否存在且有长度
  - line 574-593: 遍历 relations，匹配 source/target 名称到 concept_id
  - 逻辑正确，应该能正常渲染
```

> **最可能的根因**：`data.js` 是旧版本（在 `export_data.py` 升级前生成的），不包含 `relations` 字段。重新运行 `python export_data.py` 即可修复。
