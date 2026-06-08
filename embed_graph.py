#!/usr/bin/env python3
"""Generate knowledge graph SVG and embed into index.html as tab4 replacement."""
import json, os, math, random, re

# Read data
with open('concept_relations.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

nodes = data['nodes']
edges = data['edges']
node_map = {n['name']: n for n in nodes}

DOMAIN_COLORS = {
    '物质科学': '#e67e22',
    '生命科学': '#27ae60',
    '地球宇宙': '#2980b9',
    '技术工程': '#8e44ad',
    '综合': '#95a5a6'
}
DOMAIN_LABELS = list(DOMAIN_COLORS.keys())

# Rebuild edge index by name
edge_index_by_name = {}
for e in edges:
    edge_index_by_name.setdefault(e['source'], []).append(e['target'])
    edge_index_by_name.setdefault(e['target'], []).append(e['source'])

# Generate force-directed layout in JS
# We'll precompute positions in Python for stability

# 1. Group by domain and arrange in a radial layout
domain_nodes = {}
for n in nodes:
    domain_nodes.setdefault(n['domain'], []).append(n)

# Precompute positions
positions = {}
domain_order = ['物质科学', '生命科学', '地球宇宙', '技术工程', '综合']
angles = [0, 72, 144, 216, 288]  # 5 domains, 72 degrees apart
for idx, domain in enumerate(domain_order):
    ns = domain_nodes.get(domain, [])
    if not ns:
        continue
    center_angle = math.radians(angles[idx])
    cx = 400 + 250 * math.cos(center_angle)
    cy = 250 + 250 * math.sin(center_angle)
    radius = 30 + 15 * len(ns)
    for i, n in enumerate(ns):
        angle = center_angle + math.radians(i * (360 / max(len(ns), 1)))
        maxwc = max(w['wrong_count'] for w in nodes) or 1
        r = radius + 20 * (n['wrong_count'] / maxwc)
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        positions[n['name']] = (px, py)

# Clamp positions to valid SVG area
svg_w, svg_h = 800, 500

# Generate HTML
max_wrong = max(n['wrong_count'] for n in nodes) or 1

html_parts = []

html_parts.append('''<!-- ── 知识图谱 ── -->
<div class="sec" id="sec4">
<div style="margin-bottom:10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center">
  <select id="graph-filter" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:var(--card)">
    <option value="all">🌐 全部领域</option>
''')
for d in DOMAIN_LABELS:
    color = DOMAIN_COLORS[d]
    html_parts.append(f'    <option value="{d}">{d}</option>\n')
html_parts.append('''  </select>
  <span style="font-size:11.5px;color:var(--text2)">节点大小 = 错题数 | 颜色 = 领域</span>
</div>
<div style="display:flex;flex-wrap:wrap;gap:12px">
<div style="flex:1;min-width:280px;background:var(--card);border-radius:10px;padding:8px;border:1px solid var(--border);overflow:hidden">
<svg id="graph-svg" width="100%" viewBox="0 0 800 500" style="display:block;background:var(--bg2);border-radius:8px"></svg>
</div>
''')

# TOP10 wrong rank (right panel)
top10 = sorted(nodes, key=lambda n: n['wrong_count'], reverse=True)[:10]
html_parts.append('''<div id="graph-rank" style="flex:0 0 200px;min-width:160px;background:var(--card);border-radius:10px;padding:12px;border:1px solid var(--border)">
  <div style="font-size:13px;font-weight:700;margin-bottom:8px;color:var(--accent)">🔴 高频错题TOP10</div>
''')
for i, n in enumerate(top10):
    color = DOMAIN_COLORS.get(n['domain'], '#95a5a6')
    name_display = n['name'] if len(n['name']) <= 18 else n['name'][:16] + '…'
    html_parts.append(f'  <div class="gr-item" data-name="{n["name"]}" onclick="focusGraphNode(\'{n["name"]}\')" style="display:flex;align-items:center;gap:6px;padding:5px 6px;border-radius:6px;cursor:pointer;font-size:12px;transition:background .15s">\n')
    html_parts.append(f'    <span style="font-weight:700;color:{color}">#{i+1}</span>\n')
    html_parts.append(f'    <span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="{n["name"]}">{name_display}</span>\n')
    html_parts.append(f'    <span style="font-weight:700;color:var(--accent)">{n["wrong_count"]}</span>\n')
    html_parts.append(f'  </div>\n')
html_parts.append('</div>\n')
html_parts.append('</div>\n')  # flex wrap
html_parts.append('''<div id="graph-detail" style="margin-top:10px;display:none;background:var(--card);border-radius:10px;padding:14px;border:1px solid var(--border)">
  <div style="font-size:15px;font-weight:700" id="gd-name"></div>
  <div style="font-size:12px;color:var(--text2);margin:4px 0" id="gd-type"></div>
  <div style="font-size:12.5px;margin:6px 0;line-height:1.5" id="gd-def"></div>
  <div style="display:flex;gap:12px;font-size:12px;margin-top:6px">
    <span id="gd-wrong" style="color:var(--accent)"></span>
    <span id="gd-total" style="color:var(--blue)"></span>
  </div>
  <div style="margin-top:6px;font-size:11.5px;color:var(--text2)" id="gd-domain"></div>
</div>
</div>
<!-- /知识图谱 -->

<script>
// ========== Knowledge Graph ==========
const GRAPH_DATA = ''')

html_parts.append(json.dumps({'nodes': nodes, 'edges': edges}, ensure_ascii=False))
html_parts.append(''';

const DOMAIN_COLORS = ''' + json.dumps(DOMAIN_COLORS, ensure_ascii=False) + ''';

let graphNodes = [];
let graphEdges = [];
let dragNode = null;
let dragOffX = 0, dragOffY = 0;

function initGraph() {
  const svg = document.getElementById('graph-svg');
  if (!svg) return;
  
  // Build node map
  const nm = {};
  GRAPH_DATA.nodes.forEach(n => { nm[n.name] = n; });
  
  // Precompute positions (radial by domain)
  const domains = ['物质科学','生命科学','地球宇宙','技术工程','综合'];
  const angles = [0, 72, 144, 216, 288];
  const positions = {};
  const maxWrong = Math.max(...GRAPH_DATA.nodes.map(n => n.wrong_count), 1);
  
  domains.forEach((d, idx) => {
    const ns = GRAPH_DATA.nodes.filter(n => n.domain === d);
    if (!ns.length) return;
    const ca = angles[idx] * Math.PI / 180;
    const cx = 400 + 220 * Math.cos(ca);
    const cy = 250 + 220 * Math.sin(ca);
    const r = 50 + 20 * ns.length;
    ns.forEach((n, i) => {
      const a = ca + (i - ns.length/2) * 0.25;
      const rr = r + 25 * (n.wrong_count / maxWrong);
      positions[n.name] = [cx + rr * Math.cos(a), cy + rr * Math.sin(a)];
    });
  });
  
  // Force-directed layout: simple spring model
  // Initial positions
  GRAPH_DATA.nodes.forEach(n => {
    if (!positions[n.name]) positions[n.name] = [Math.random()*600+100, Math.random()*300+100];
  });
  const pos = JSON.parse(JSON.stringify(positions));
  
  // Run force simulation (100 iterations)
  for (let iter = 0; iter < 120; iter++) {
    const forces = {};
    GRAPH_DATA.nodes.forEach(n => { forces[n.name] = [0, 0]; });
    
    // Repulsion: all pairs repel
    for (let i = 0; i < GRAPH_DATA.nodes.length; i++) {
      for (let j = i+1; j < GRAPH_DATA.nodes.length; j++) {
        const a = GRAPH_DATA.nodes[i], b = GRAPH_DATA.nodes[j];
        const dx = pos[a.name][0] - pos[b.name][0];
        const dy = pos[a.name][1] - pos[b.name][1];
        const dist = Math.sqrt(dx*dx + dy*dy) || 1;
        const rep = 1500 / (dist * dist + 1);
        forces[a.name][0] += rep * dx / dist;
        forces[a.name][1] += rep * dy / dist;
        forces[b.name][0] -= rep * dx / dist;
        forces[b.name][1] -= rep * dy / dist;
      }
    }
    
    // Attraction: connected nodes attract
    GRAPH_DATA.edges.forEach(e => {
      const a = pos[e.source], b = pos[e.target];
      if (!a || !b) return;
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const dist = Math.sqrt(dx*dx + dy*dy) || 1;
      const att = 0.003 * dist;
      forces[e.source][0] += att * dx;
      forces[e.source][1] += att * dy;
      forces[e.target][0] -= att * dx;
      forces[e.target][1] -= att * dy;
    });
    
    // Center gravity
    GRAPH_DATA.nodes.forEach(n => {
      forces[n.name][0] += (400 - pos[n.name][0]) * 0.001;
      forces[n.name][1] += (250 - pos[n.name][1]) * 0.001;
    });
    
    // Apply forces with damping
    const damping = 0.85;
    GRAPH_DATA.nodes.forEach(n => {
      pos[n.name][0] = Math.max(20, Math.min(780, pos[n.name][0] + forces[n.name][0] * damping));
      pos[n.name][1] = Math.max(20, Math.min(480, pos[n.name][1] + forces[n.name][1] * damping));
    });
  }
  
  graphNodes = GRAPH_DATA.nodes.map(n => ({
    ...n,
    x: pos[n.name][0],
    y: pos[n.name][1]
  }));
  graphEdges = GRAPH_DATA.edges;
  
  renderGraph('all');
}

function renderGraph(filter) {
  const svg = document.getElementById('graph-svg');
  if (!svg) return;
  
  // Filter nodes
  const visibleNodes = filter === 'all' 
    ? graphNodes 
    : graphNodes.filter(n => n.domain === filter);
  const visibleNames = new Set(visibleNodes.map(n => n.name));
  
  // Filter edges (both endpoints visible)
  const visibleEdges = graphEdges.filter(e => 
    visibleNames.has(e.source) && visibleNames.has(e.target)
  );
  
  const maxWrong = Math.max(...graphNodes.map(n => n.wrong_count), 1);
  
  // Clear
  svg.innerHTML = '';
  
  // Draw edges
  visibleEdges.forEach(e => {
    const src = graphNodes.find(n => n.name === e.source);
    const tgt = graphNodes.find(n => n.name === e.target);
    if (!src || !tgt) return;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', src.x);
    line.setAttribute('y1', src.y);
    line.setAttribute('x2', tgt.x);
    line.setAttribute('y2', tgt.y);
    line.setAttribute('stroke', '#ddd');
    line.setAttribute('stroke-width', '1');
    line.setAttribute('stroke-dasharray', e.relation === '包含' ? '' : '3,3');
    line.dataset.source = e.source;
    line.dataset.target = e.target;
    line.addEventListener('mouseenter', function() { this.setAttribute('stroke', '#c0392b'); this.setAttribute('stroke-width', '2'); });
    line.addEventListener('mouseleave', function() { this.setAttribute('stroke', '#ddd'); this.setAttribute('stroke-width', '1'); });
    svg.appendChild(line);
  });
  
  // Draw nodes
  visibleNodes.forEach(n => {
    const r = Math.max(5, Math.min(22, 4 + 18 * (n.wrong_count / maxWrong)));
    const color = DOMAIN_COLORS[n.domain] || '#95a5a6';
    
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = 'pointer';
    g.dataset.name = n.name;
    
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', n.x);
    circle.setAttribute('cy', n.y);
    circle.setAttribute('r', r);
    circle.setAttribute('fill', color);
    circle.setAttribute('fill-opacity', '0.8');
    circle.setAttribute('stroke', '#fff');
    circle.setAttribute('stroke-width', '2');
    g.appendChild(circle);
    
    // Label
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', n.x);
    label.setAttribute('y', n.y + 4);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '9');
    label.setAttribute('fill', '#333');
    label.setAttribute('pointer-events', 'none');
    // Truncate label
    let displayName = n.name.length > 10 ? n.name.substring(0, 8) + '..' : n.name;
    label.textContent = displayName;
    g.appendChild(label);
    
    // Click
    g.addEventListener('click', function() { showGraphDetail(n.name); });
    
    // Drag
    g.addEventListener('mousedown', function(e) {
      dragNode = { name: n.name, x: n.x, y: n.y, r: r };
      const rect = svg.getBoundingClientRect();
      dragOffX = e.clientX - rect.left;
      dragOffY = e.clientY - rect.top;
      e.preventDefault();
    });
    
    svg.appendChild(g);
  });
}

// Drag handling
document.addEventListener('mousemove', function(e) {
  if (!dragNode) return;
  const svg = document.getElementById('graph-svg');
  const rect = svg.getBoundingClientRect();
  const scaleX = 800 / rect.width;
  const scaleY = 500 / rect.height;
  const nx = (e.clientX - rect.left) * scaleX;
  const ny = (e.clientY - rect.top) * scaleY;
  
  // Update node position
  const nd = graphNodes.find(n => n.name === dragNode.name);
  if (nd) {
    nd.x = Math.max(20, Math.min(780, nx));
    nd.y = Math.max(20, Math.min(480, ny));
  }
  
  // Re-render
  const filter = document.getElementById('graph-filter').value || 'all';
  renderGraph(filter);
  
  // Update drag position
  dragNode.x = nd ? nd.x : dragNode.x;
  dragNode.y = nd ? nd.y : dragNode.y;
});
document.addEventListener('mouseup', function() { dragNode = null; });

function showGraphDetail(name) {
  const n = graphNodes.find(node => node.name === name);
  if (!n) return;
  
  document.getElementById('gd-name').textContent = n.symbol + ' ' + n.name;
  document.getElementById('gd-type').textContent = n.type + ' · ' + n.domain;
  document.getElementById('gd-def').textContent = n.definition || '暂无定义';
  document.getElementById('gd-wrong').textContent = '\u2717 错题 ' + n.wrong_count + ' 题';
  document.getElementById('gd-total').textContent = '\u2139 总题 ' + n.total_questions + ' 题';
  document.getElementById('gd-domain').textContent = '\ud83c\udf10 ' + n.domain;
  document.getElementById('graph-detail').style.display = 'block';
}

function focusGraphNode(name) {
  // Highlight the node by re-rendering with emphasis
  const filter = document.getElementById('graph-filter').value || 'all';
  renderGraph(filter);
  showGraphDetail(name);
}

// Filter change
document.addEventListener('DOMContentLoaded', function() {
  const filter = document.getElementById('graph-filter');
  if (filter) {
    filter.addEventListener('change', function() {
      document.getElementById('graph-detail').style.display = 'none';
      renderGraph(this.value);
    });
  }
  initGraph();
});

// Re-init when tab shown
window.initGraph = initGraph;
</script>''')

html_str = ''.join(html_parts)

# ── Read HTML and replace sec4 ──
with open('docs/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace from <!-- ── 思维导图 ── --> to next <!-- /思维导图 --> (or end of sec4)
# Find the section
pattern = r'<!-- ── 思维导图 ── -->.*?(?=</div>\s*<!-- /思维导图 -->)'
replacement = html_str

html_new = re.sub(pattern, replacement, html, count=1, flags=re.DOTALL)

# Also update nav text
html_new = html_new.replace(
    'id="tab4">🕸 思维导图</div>',
    'id="tab4">🕸 知识图谱</div>'
)

# Add knowledge graph ranking CSS
css_to_add = '''
.gr-item:hover{background:var(--accent-light)}
#graph-svg{min-height:360px}
@media(max-width:600px){#graph-rank{flex:1 1 100%}}
'''
# Insert before last </style>
html_new = html_new.replace('</style>', css_to_add + '\n</style>')

with open('docs/index.html', 'w', encoding='utf-8') as f:
    f.write(html_new)

print('Knowledge graph embedded into index.html')
print(f'Nodes: {len(nodes)}, Edges: {len(edges)}')
print(f'TOP10 wrong: {[(n["name"][:20], n["wrong_count"]) for n in top10]}')
