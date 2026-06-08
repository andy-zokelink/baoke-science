#!/usr/bin/env python3
"""Regenerate 错题本 section in docs/index.html from database."""
import sqlite3, os, re
from collections import Counter, defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baoke_learning.db')
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'index.html')

# ── Domain keyword matching (same logic as update_html_concepts.py) ──
TECH_KW = ['工程', '结构', '材料', '设计', '仿生', '稳定性', '框架', '塔台', '建筑', '斜面', '轮轴', '杠杆', '滑轮', '机械', '工具']
LIFE_KW = ['生物', '遗传', '变异', '细胞', '植物', '动物', '微生物', '环境', '生态', '分类', '多样性', '基因', '孟德尔', '进化', '人体', '健康', '食物', '营养', '消化']
MATTER_KW = ['物质', '化学', '物理', '能量', '电', '磁', '力', '光', '热', '声', '金属', '铁', '二氧化碳', '淀粉', '碘', '溶液', '溶解', '燃烧', '反应', '显微镜', '放大镜', '分子', '原子']
EARTH_KW = ['地球', '太阳', '月球', '行星', '星座', '银河', '宇宙', '天文', '日食', '月食', '季节', '气候', '天气', '北极星', '化石', '地质', '能源', '矿产', '煤', '石油', '大气', '水循环']

DOMAIN_COLORS = {
    '物质科学': '#e67e22',
    '生命科学': '#27ae60',
    '地球宇宙': '#2980b9',
    '技术工程': '#8e44ad',
    '综合': '#95a5a6',
}

def classify_domain(kp, qtext):
    """Classify a wrong answer into domain using knowledge_point and question_text."""
    text = (kp or '') + ' ' + (qtext or '')
    scores = {'tech': 0, 'life': 0, 'matter': 0, 'earth': 0}
    for kw in TECH_KW:
        if kw in text: scores['tech'] += 1
    for kw in LIFE_KW:
        if kw in text: scores['life'] += 1
    for kw in MATTER_KW:
        if kw in text: scores['matter'] += 1
    for kw in EARTH_KW:
        if kw in text: scores['earth'] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return '综合'
    return {'tech': '技术工程', 'life': '生命科学', 'matter': '物质科学', 'earth': '地球宇宙'}[best]

def get_concept_type_emoji(ct_name):
    m = {'核心概念': '★★★', '常考概念': '★★', '易错概念': '★', '边缘概念': '·'}
    return m.get(ct_name, '★★')

def get_concept_badge_class(ct_name):
    m = {'核心概念': 'core', '常考概念': 'common', '易错概念': 'trap', '边缘概念': 'edge'}
    return m.get(ct_name, 'common')

# ── Read data ──
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Get wrong answers with concept info
wrongs = conn.execute('''
    SELECT sa.*, rq.question_text, rq.question_number, rq.knowledge_point,
           rq.options, rq.correct_answer, rq.difficulty,
           sp.page_number, sm.title as source_title,
           c.name as concept_name, ct.name as concept_type, ct.symbol
    FROM student_answers sa
    JOIN raw_questions rq ON sa.question_id = rq.id
    JOIN source_pages sp ON rq.source_page_id = sp.id
    JOIN source_materials sm ON rq.material_id = sm.id
    LEFT JOIN concepts c ON rq.concept_id = c.id
    LEFT JOIN concept_types ct ON c.concept_type_id = ct.id
    WHERE sa.is_correct = '✗'
    ORDER BY sa.id
''').fetchall()

# Total correct for accuracy
total_correct = conn.execute("SELECT COUNT(*) FROM student_answers WHERE is_correct='✓'").fetchone()[0]
total_q = conn.execute("SELECT COUNT(*) FROM raw_questions").fetchone()[0]
total_answers = conn.execute("SELECT COUNT(*) FROM student_answers").fetchone()[0]
accuracy = round(total_correct / total_answers * 100) if total_answers > 0 else 0

# Get question types for each wrong answer (before closing conn)
wrong_with_concepts = []
for w in wrongs:
    qid = w['id']  # Use student_answers.id
    qt_row = conn.execute("SELECT qt.name FROM raw_questions rq JOIN question_types qt ON rq.question_type_id=qt.id WHERE rq.id=?", (w['question_id'],)).fetchone()
    qtype_name = qt_row['name'] if qt_row else '未知'
    
    kp = w['knowledge_point'] or ''
    qtext = w['question_text'] or ''
    domain = classify_domain(kp, qtext)
    ct = w['concept_type'] or '常考概念'
    wrong_with_concepts.append({**dict(w), 'domain': domain, 'ct_name': ct, 'qtype': qtype_name})

conn.close()

# ── Compute stats ──
total_wrong = len(wrong_with_concepts)

# Domain breakdown
domain_counts = Counter(w['domain'] for w in wrong_with_concepts)
domain_order = ['物质科学', '综合', '生命科学', '地球宇宙', '技术工程']
domain_items = [(d, domain_counts.get(d, 0)) for d in domain_order if domain_counts.get(d, 0) > 0]
max_domain = max(c for _, c in domain_items) if domain_items else 1

# KP error stats
kp_counter = Counter(w['knowledge_point'] or '未知' for w in wrong_with_concepts)
top_kps = kp_counter.most_common(12)
max_kp = top_kps[0][1] if top_kps else 1

# Question type stats
qtype_counter = Counter(w['qtype'] for w in wrong_with_concepts)

# Error cause stats
ec_counter = Counter(w['error_cause'] for w in wrong_with_concepts if w['error_cause'])
distinct_kps = len(set(w['knowledge_point'] for w in wrong_with_concepts if w['knowledge_point']))

# ── Generate HTML ──
lines = []
lines.append('<!-- ── 错题本 ── -->')
lines.append('<div class="sec" id="sec3">')

# Stats overview
lines.append('<div class="wstat-box">')
lines.append('  <h3>📊 错题统计概览</h3>')
lines.append('  <div class="wstat-nums">')
lines.append(f'    <div class="wstat-num"><div class="big">{total_wrong}</div><div class="lbl">总错题数</div></div>')
lines.append(f'    <div class="wstat-num ok"><div class="big">{total_correct}</div><div class="lbl">历史答对</div></div>')
lines.append(f'    <div class="wstat-num warn"><div class="big" id="wb-accuracy">{accuracy}%</div><div class="lbl">正确率</div></div>')
lines.append('  </div>')

# Domain breakdown chart
lines.append('  <div class="chart-section">')
lines.append('    <h4>📍 薄弱领域 TOP5（错题数）</h4>')
for domain, count in domain_items:
    pct = round(count / max_domain * 100)
    color = DOMAIN_COLORS.get(domain, '#95a5a6')
    lines.append('    <div class="bar-row">')
    lines.append(f'  <div class="bar-label">{domain}</div>')
    lines.append(f'  <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>')
    lines.append(f'  <div class="bar-cnt">{count}</div>')
    lines.append('</div>')
lines.append('  </div>')
lines.append('</div>')

# TOP12 KPs
lines.append('<div class="wstat-box">')
lines.append('  <h3>🔥 高频错误知识点 TOP12</h3>')
lines.append('  <div class="chart-section">')
for kp, cnt in top_kps:
    pct = round(cnt / max_kp * 100)
    display_kp = kp if len(kp) <= 18 else kp[:16] + '…'
    title_kp = kp.replace('"', '&quot;')
    lines.append('    <div class="bar-row">')
    lines.append(f'  <div class="bar-label" title="{title_kp}">{display_kp}</div>')
    lines.append(f'  <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:#c0392b"></div></div>')
    lines.append(f'  <div class="bar-cnt">{cnt}</div>')
    lines.append('</div>')
lines.append('  </div>')
lines.append('</div>')

# Analysis
# Get top types
type_text = '、'.join(f'{t}{c}道' for t, c in qtype_counter.most_common(3))
lines.append('<div class="wpattern">')
lines.append('  <h4>📝 出题规律分析</h4>')
top_domain = domain_items[0][0] if domain_items else '综合'
lines.append(f'  <p>① <b>{top_domain}</b>是最大失分领域（{domain_items[0][1]}题），重点集中在核心概念辨析和实验应用。<br>')
lines.append(f'  ② 大多数错题(<b>{distinct_kps}个知识点，每点1-3错</b>)分布极为分散，说明知识面薄弱而非个别盲点，需系统复习。<br>')
lines.append(f'  ③ {top_kps[0][0] if top_kps else ""}、{top_kps[1][0] if len(top_kps)>1 else ""}类是相对高频错误点，优先强化。<br>')
lines.append(f'  ④ 「{type_text}」是主要错题类型，建议针对性强化。</p>')
lines.append('</div>')

# Filter bar
lines.append('<div class="wfbar">')
lines.append(f'  <button class="fbtn on" onclick="filterWrong(\'all\',this)">全部（{total_wrong}）</button>')
lines.append('  <button class="fbtn" onclick="filterWrong(\'has\',this)">有分析</button>')
lines.append('</div>')
lines.append('')

# ── Wrong answer cards ──
for i, w in enumerate(wrong_with_concepts):
    qtext = (w['question_text'] or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    kp = (w['knowledge_point'] or '未分类')
    student_resp = (w['student_response'] or '未作答')
    error_cause = (w['error_cause'] or '暂无分析')
    exam_strategy = (w['exam_strategy'] or '暂无')
    source = w['source_title'] or '未知来源'
    page = w['page_number'] or '?'
    ct_name = w['ct_name']
    symbol = w['symbol'] or get_concept_type_emoji(ct_name)
    badge_class = get_concept_badge_class(ct_name)
    domain = w['domain']

    # Truncate error_cause if too long (keep first 120 chars)
    if len(error_cause) > 120:
        error_cause = error_cause[:117] + '...'

    lines.append(f'<div class="wcard" id="wrong-{i}">')
    lines.append('  <div class="wchdr">')
    lines.append(f'    <span class="wcn">错题 #{i+1}</span>')
    lines.append(f'    <span class="wckp" title="{kp.replace(chr(34), "&quot;")}">{kp if len(kp)<=20 else kp[:18]+"…"}</span>')
    lines.append(f'    <span style="font-size:9.5px;background:var(--accent-light);color:var(--accent);border-radius:3px;padding:1px 5px">{symbol} {ct_name}</span>')
    lines.append('  </div>')
    lines.append(f'  <div class="wq" title="{qtext}">{qtext if len(qtext)<=60 else qtext[:58]+"…"}</div>')
    lines.append('  <div class="wa">')
    lines.append(f'    <span class="wal">你的作答：</span>')
    lines.append(f'    <span class="wav">✗ {student_resp}</span>')
    lines.append('  </div>')
    lines.append(f'  <div class="we">💡 {error_cause}</div>')
    lines.append(f'  <div class="ws">🎯 出题思路：{exam_strategy}</div>')
    lines.append(f'  <div class="wsrc">📄 {source} · P{page} · {domain}</div>')
    lines.append('</div>')
    lines.append('')

lines.append('</div>')
lines.append('<!-- /错题本 -->')

new_wrong_section = '\n'.join(lines)

# ── Read HTML and replace ──
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

# Find the section to replace
# From <!-- ── 错题本 ── --> to just before <!-- ── 思维导图 ── -->
pattern = r'<!-- ── 错题本 ── -->.*?(?=<!-- ── 思维导图 ── -->)'
replacement = new_wrong_section

html_new = re.sub(pattern, replacement, html, count=1, flags=re.DOTALL)

# Also fix the tab badge count
html_new = html_new.replace(
    '<div class="nav-t" onclick="showTab(3)" id="tab3">📕 错题本 <span class="bdg">80</span></div>',
    f'<div class="nav-t" onclick="showTab(3)" id="tab3">📕 错题本 <span class="bdg">{total_wrong}</span></div>'
)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html_new)

print(f'Done! Regenerated 错题本: {total_wrong} wrong answers, {len(domain_items)} domains, {len(top_kps)} top KPs')
print(f'Accuracy: {accuracy}% ({total_correct}/{total_answers})')
