#!/usr/bin/env python3
"""Regenerate CONCEPTS JSON in HTML from database."""
import sqlite3, json, re, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baoke_learning.db')
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pages', '科学备考.html')

# Read all concepts from DB
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

concepts = conn.execute('''
    SELECT c.id, c.name, c.definition, c.analogy, c.example, c.counter_example,
           ct.name as type_name, ct.symbol, ct.priority, c.unit
    FROM concepts c
    JOIN concept_types ct ON c.concept_type_id = ct.id
    ORDER BY c.id
''').fetchall()

# Build CONCEPTS dict
concepts_dict = {}
for c in concepts:
    # Determine domain from concept name/type
    name = c['name']
    type_name = c['type_name']
    
    # Domain mapping
    domain = '综合'
    dk = 'other'
    
    tech_keywords = ['工程', '结构', '材料', '设计', '仿生', '稳定性', '框架', '塔台', '建筑', '斜面', '轮轴', '杠杆', '滑轮']
    life_keywords = ['生物', '遗传', '变异', '细胞', '植物', '动物', '微生物', '环境', '生态', '分类', '多样性', '基因', '孟德尔', '进化', '人体', '健康']
    matter_keywords = ['物质', '化学', '物理', '能量', '电', '磁', '力', '光', '热', '声', '金属', '铁', '二氧化碳', '淀粉', '碘', '溶液', '溶解', '燃烧', '反应', '显微镜', '放大镜']
    earth_keywords = ['地球', '太阳', '月球', '行星', '星座', '银河', '宇宙', '天文', '日食', '月食', '季节', '气候', '天气', '北极星', '化石', '地质', '能源', '矿产', '煤', '石油']
    
    scores = {'tech': 0, 'life': 0, 'matter': 0, 'earth': 0, 'other': 0}
    for kw in tech_keywords:
        if kw in name: scores['tech'] += 1
    for kw in life_keywords:
        if kw in name: scores['life'] += 1
    for kw in matter_keywords:
        if kw in name: scores['matter'] += 1
    for kw in earth_keywords:
        if kw in name: scores['earth'] += 1
    
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        domain = '综合'
    elif best == 'tech':
        domain = '技术工程'
    elif best == 'life':
        domain = '生命科学'
    elif best == 'matter':
        domain = '物质科学'
    elif best == 'earth':
        domain = '地球宇宙'
    
    # Domain key
    dk_map = {'技术工程': 'tech', '生命科学': 'life', '物质科学': 'matter', '地球宇宙': 'earth', '综合': 'other'}
    dk = dk_map.get(domain, 'other')
    
    concepts_dict[str(c['id'])] = {
        'id': c['id'],
        'name': c['name'],
        'definition': c['definition'] or '',
        'analogy': c['analogy'],
        'example': c['example'],
        'counter_example': c['counter_example'],
        'symbol': c['symbol'],
        'type_name': c['type_name'],
        'priority': c['priority'],
        'domain': domain,
        'dk': dk
    }

conn.close()

# Generate JSON string (matching original format: single line, double quotes)
concepts_json = json.dumps(concepts_dict, ensure_ascii=False, separators=(', ', ': '))

# Read HTML
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace CONCEPTS
# Pattern: const CONCEPTS = {...};
old_pattern = r'const CONCEPTS = \{.*?\};'
new_line = f'const CONCEPTS = {concepts_json};'

html = re.sub(old_pattern, new_line, html, count=1, flags=re.DOTALL)

# Write back
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

# Verify
concept_count = len(concepts_dict)
empty_defs = sum(1 for c in concepts_dict.values() if not c['definition'])
print(f'Updated CONCEPTS in HTML: {concept_count} concepts, {empty_defs} empty definitions')
