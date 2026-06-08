#!/usr/bin/env python3
"""Build concept_relations.json - domain-based clustering for knowledge graph."""
import sqlite3, json

conn = sqlite3.connect('baoke_learning.db')
conn.row_factory = sqlite3.Row

concepts = conn.execute('''
    SELECT c.*, ct.name as type_name, ct.symbol 
    FROM concepts c 
    JOIN concept_types ct ON c.concept_type_id = ct.id
    ORDER BY c.id
''').fetchall()

wrong_by_concept = {}
for row in conn.execute('''
    SELECT rq.concept_id, COUNT(*) as cnt
    FROM student_answers sa
    JOIN raw_questions rq ON sa.question_id = rq.id
    WHERE sa.is_correct = '\u2717' AND rq.concept_id IS NOT NULL
    GROUP BY rq.concept_id
'''):
    wrong_by_concept[row['concept_id']] = row['cnt']

total_by_concept = {}
for row in conn.execute('''
    SELECT rq.concept_id, COUNT(*) as cnt
    FROM raw_questions rq
    WHERE rq.concept_id IS NOT NULL
    GROUP BY rq.concept_id
'''):
    total_by_concept[row['concept_id']] = row['cnt']

DOMAIN_KW = {
    '\u7269\u8d28\u79d1\u5b66': ['\u7535','\u78c1','\u529b','\u70ed','\u5149','\u58f0','\u7269\u8d28','\u5316\u5b66','\u7269\u7406','\u80fd\u91cf','\u91d1\u5c5e','\u94c1','\u71c3\u70e7','\u53cd\u5e94','\u5206\u5b50','\u539f\u5b50','\u6eb6\u6db2','\u6eb6\u89e3','\u653e\u5927\u955c','\u663e\u5fae\u955c','\u7b80\u5355\u673a\u68b0','\u6746\u6746','\u6ed1\u8f6e','\u659c\u9762','\u8f6e\u8f74','\u4f20\u52a8','\u9f7f\u8f6e','\u5bfc\u4f53','\u7edd\u7f18','\u6469\u64e6','\u60ef\u6027','\u91cd\u529b','\u6d6e\u529b','\u5f39\u529b','\u538b\u529b','\u538b\u5f3a','\u6e29\u5ea6','\u70ed\u91cf'],
    '\u751f\u547d\u79d1\u5b66': ['\u751f\u7269','\u7ec6\u80de','\u690d\u7269','\u52a8\u7269','\u5fae\u751f\u7269','\u9057\u4f20','\u57fa\u56e0','\u8fdb\u5316','\u751f\u6001','\u73af\u5883','\u4eba\u4f53','\u5065\u5eb7','\u8425\u517b','\u98df\u7269','\u6d88\u5316','\u547c\u5438','\u795e\u7ecf','\u7e41\u6b96','\u53d1\u80b2','\u53d8\u5f02','\u7ec4\u7ec7','\u5668\u5b98','\u7cfb\u7edf','\u79cd\u7fa4','\u98df\u7269\u94fe'],
    '\u5730\u7403\u5b87\u5b99': ['\u5730\u7403','\u592a\u9633','\u6708\u7403','\u884c\u661f','\u661f\u5ea7','\u94f6\u6cb3','\u5b87\u5b99','\u5929\u6587','\u5316\u77f3','\u5730\u8d28','\u6c14\u5019','\u5929\u6c14','\u5b63\u8282','\u6708\u76f8','\u65e5\u98df','\u6708\u98df','\u516c\u8f6c','\u81ea\u8f6c','\u663c\u591c','\u5317\u6781\u661f','\u5317\u6597','\u661f\u7a7a','\u592a\u9633\u7cfb','\u9635\u77f3','\u5730\u9707','\u706b\u5c71','\u5ca9\u77f3','\u77ff\u7269','\u7164','\u77f3\u6cb9','\u5927\u6c14','\u6d77\u6d0b'],
    '\u6280\u672f\u5de5\u7a0b': ['\u5de5\u7a0b','\u7ed3\u6784','\u6750\u6599','\u8bbe\u8ba1','\u5efa\u7b51','\u673a\u68b0','\u6280\u672f','\u53d1\u660e','\u5236\u4f5c','\u5de5\u5177','\u6d4b\u8bd5','\u6539\u8fdb','\u4ea7\u54c1','\u9700\u6c42','\u65b9\u6848','\u8bc4\u4f30','\u642d\u5efa','\u6a21\u578b','\u5854\u53f0','\u6846\u67b6','\u7a33\u5b9a\u6027','\u4eff\u751f'],
}

def classify_domain(name, definition):
    text = (name or '') + ' ' + (definition or '')
    scores = {}
    for d, kws in DOMAIN_KW.items():
        scores[d] = sum(1 for kw in kws if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else '\u7efc\u5408'

# Build nodes
nodes = []
node_map = {}
for c in concepts:
    domain = classify_domain(c['name'], c['definition'] or '')
    wc = wrong_by_concept.get(c['id'], 0)
    tc = total_by_concept.get(c['id'], 0)
    node = {
        'id': c['id'],
        'name': c['name'],
        'definition': c['definition'] or '',
        'type': c['type_name'],
        'symbol': c['symbol'],
        'domain': domain,
        'wrong_count': wc,
        'total_questions': tc
    }
    nodes.append(node)
    node_map[c['name']] = node

# Domain groups
domain_groups = {}
for n in nodes:
    domain_groups.setdefault(n['domain'], []).append(n['name'])

edges = []
edge_set = set()

# For each domain, create a chain: A-B, B-C, C-D (like a timeline)
# and also connect concepts that share the same first 4 chars
for domain, names in domain_groups.items():
    # Sort by id to get stable order
    domain_ns = sorted([n for n in nodes if n['name'] in names], key=lambda x: x['id'])
    
    # Chain connections: each concept connects to next 3
    for i in range(len(domain_ns)):
        for j in range(1, min(4, len(domain_ns) - i)):
            a, b = domain_ns[i], domain_ns[i+j]
            key = tuple(sorted([a['name'], b['name']]))
            if key not in edge_set:
                edges.append({'source': a['name'], 'target': b['name'], 'relation': '\u5e76\u5217'})
                edge_set.add(key)

connected_names = set()
for e in edges:
    connected_names.add(e['source'])
    connected_names.add(e['target'])

output = {'nodes': nodes, 'edges': edges}
with open('concept_relations.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

domain_stats = {}
for n in nodes:
    domain_stats[n['domain']] = domain_stats.get(n['domain'], 0) + 1

print(f'Nodes: {len(nodes)}')
print(f'Edges: {len(edges)}')
rel_types = {}
for e in edges:
    rel_types[e['relation']] = rel_types.get(e['relation'], 0) + 1
print(f'Relation types: {rel_types}')
print(f'Domain breakdown: {domain_stats}')
isolated = sum(1 for n in nodes if n['name'] not in connected_names)
print(f'Isolated after linking: {isolated}')

conn.close()
