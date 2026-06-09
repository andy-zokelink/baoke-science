#!/usr/bin/env python3
"""分析 concepts 表，提取概念之间的显式关系，输出 concept_relations.json

增强策略（目标：182节点 → 300+边）：
1. 保持已有的 keyword_deps 精确匹配
2. 基于 domain 分组，同 domain 内建立"同域"连接（每个节点连3-5个最相似的）
3. 基于 definition 文本相似度（共享关键词）建立边
4. 概念名子串匹配：如果概念A的名称包含在概念B的名称中，建立包含/依赖关系
"""
import sqlite3, os, json, re
from collections import Counter, defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baoke_learning.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ═══ 第一步：读取数据 ═══

with get_conn() as conn:
    # 1. concept_types
    types = {r['id']: {'name': r['name'], 'symbol': r['symbol']}
             for r in conn.execute("SELECT id, name, symbol FROM concept_types").fetchall()}
    print(f"概念类型数: {len(types)}")
    for tid, t in types.items():
        print(f"  type {tid}: {t['name']} ({t['symbol']})")

    # 2. concepts
    concepts_raw = conn.execute("""
        SELECT c.id, c.name, c.definition, c.concept_type_id, c.course_id
        FROM concepts c ORDER BY c.id
    """).fetchall()
    print(f"\n概念总数: {len(concepts_raw)}")

    # 3. raw_questions → concept mapping
    questions_raw = conn.execute("""
        SELECT rq.id AS qid, rq.question_text, rq.concept_id, rq.knowledge_point
        FROM raw_questions rq
        WHERE rq.concept_id IS NOT NULL
    """).fetchall()
    q_by_concept = {}
    for q in questions_raw:
        cid = q['concept_id']
        q_by_concept.setdefault(cid, []).append({'qid': q['qid'], 'kp': q['knowledge_point']})
    print(f"题目总数(有概念关联): {len(questions_raw)}")

    # 4. student_answers → wrong count per concept
    wrong_counts = {}
    for cid in q_by_concept:
        qids = [q['qid'] for q in q_by_concept[cid]]
        placeholders = ','.join('?' * len(qids))
        row = conn.execute(f"""
            SELECT COUNT(*) as wrong
            FROM student_answers sa
            WHERE sa.question_id IN ({placeholders}) AND sa.is_correct = 0
        """, qids).fetchone()
        wrong_counts[cid] = row['wrong'] if row else 0

    total_counts = {}
    for cid, qlist in q_by_concept.items():
        total_counts[cid] = len(qlist)

# ═══ 第二步：分析概念关系 ═══

# 领域关键词映射
DOMAIN_RULES = {
    "物质科学": ['电', '磁', '力', '热', '光', '声', '物质', '化学', '物理', '能量',
                 '金属', '铁', '燃烧', '反应', '分子', '原子', '溶液', '溶解',
                 '密度', '压强', '浮力', '杠杆', '滑轮', '简单机械', '电路', '电磁'],
    "生命科学": ['生物', '细胞', '植物', '动物', '微生物', '遗传', '基因', '进化',
                 '生态', '环境', '人体', '健康', '营养', '食物', '消化', '呼吸',
                 '循环', '神经', '骨骼', '肌肉', '仿生'],
    "地球宇宙": ['地球', '太阳', '月球', '行星', '星座', '银河', '宇宙', '天文',
                 '化石', '地质', '气候', '天气', '季节', '恒星', '卫星',
                 '日食', '月食', '月相', '自转', '公转'],
    "技术工程": ['工程', '结构', '材料', '设计', '建筑', '机械', '杠杆', '滑轮',
                 '斜面', '工具', '简单机械', '稳定性', '框架', '重心', '塔台',
                 '评价', '功能', '优化', '测试', '承重', '抗震'],
}

def classify_domain(name, definition):
    text = name + (definition or '')
    scores = {}
    for domain, keywords in DOMAIN_RULES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[domain] = score
    if scores:
        return max(scores, key=scores.get)
    return "其他"

# 构建所有概念的字典
concepts = {}
for r in concepts_raw:
    ct = types.get(r['concept_type_id'], {})
    concepts[r['id']] = {
        'id': r['id'],
        'name': r['name'],
        'definition': r['definition'] or '',
        'type_name': ct.get('name', '未知'),
        'symbol': ct.get('symbol', ''),
        'domain': classify_domain(r['name'], r['definition']),
        'wrong_count': wrong_counts.get(r['id'], 0),
        'total_questions': total_counts.get(r['id'], 0),
    }

# 定义显式关系
edges = []
edge_set = set()  # 去重用 (source, target, relation)

def add_edge(source, target, relation):
    key = (source, target, relation) if source < target else (target, source, relation)
    if source != target and key not in edge_set:
        edges.append({"source": source, "target": target, "relation": relation})
        edge_set.add(key)

# 概念名反向索引
name_to_id = {v['name']: k for k, v in concepts.items()}
id_to_name = {k: v['name'] for k, v in concepts.items()}
concept_names_set = set(concepts[cid]['name'] for cid in concepts)

# ── 获取概念名称中的分词关键词 ──
def tokenize_concept_name(name):
    """从概念名称中提取有意义的关键词（2-4个中文字符的片段）"""
    # 移除标点符号和空格
    clean = re.sub(r'[/,，、；：()（）【】""''.。·\-]', ' ', name)
    # 提取2-4字的关键词
    tokens = set()
    for i in range(len(clean)):
        for j in range(i+2, min(i+5, len(clean)+1)):
            token = clean[i:j].strip()
            if len(token) >= 2 and ' ' not in token:
                tokens.add(token)
    return tokens

# 为每个概念提取关键词
concept_tokens = {}
for cid, c in concepts.items():
    concept_tokens[cid] = tokenize_concept_name(c['name'])

# ── 匹配1: 基于domain的"同域"连接 ──
# 同domain内每个概念连接3-5个其他概念（基于名称相似度）
domain_groups = defaultdict(list)
for cid, c in concepts.items():
    domain_groups[c['domain']].append(cid)

for domain, cids in domain_groups.items():
    if len(cids) < 2:
        continue
    # 对每个概念，找同domain中名称最相似的其他概念
    for i, cid in enumerate(cids):
        c_tokens = concept_tokens[cid]
        c_name = concepts[cid]['name']
        c_def_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,4}', concepts[cid]['definition']))
        
        scored = []
        for j, other_id in enumerate(cids):
            if i == j:
                continue
            other_tokens = concept_tokens[other_id]
            other_name = concepts[other_id]['name']
            
            # 名称相似度：共享token数
            shared = len(c_tokens & other_tokens)
            # 定义相似度：共享中文字词
            other_def_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,4}', concepts[other_id]['definition']))
            def_shared = len(c_def_tokens & other_def_tokens)
            
            # 子串匹配：一个概念名包含在另一个中
            substr_match = c_name in other_name or other_name in c_name
            
            score = shared * 2 + def_shared + (3 if substr_match else 0)
            if score > 0:
                scored.append((score, other_id))
        
        # 连接最相似的3-5个
        scored.sort(reverse=True)
        max_links = min(5, len(scored))
        for rank, (score, other_id) in enumerate(scored[:max_links]):
            relation = '并列'  # 同域默认为并列
            add_edge(c_name, concepts[other_id]['name'], relation)

# ── 匹配2: 基于definition关键词匹配 ──
# 两个概念的definition有相同关键词则建立边
print("\n基于definition匹配...")
for cid, c in concepts.items():
    def_text = c['definition']
    if not def_text:
        continue
    # 提取定义中的所有2-4字关键词
    def_kws = set(re.findall(r'[\u4e00-\u9fff]{2,4}', def_text))
    # 排除通用词
    stop_words = {'一个', '一些', '可以', '通过', '进行', '称为', '这个', '就是', '不是',
                  '那么', '没有', '如果', '因为', '所以', '但是', '或者', '并且', '而且',
                  '如何', '什么', '可能', '不能', '需要', '具有', '之间', '过程'}
    def_kws -= stop_words
    
    # 找其他概念，其名称出现在此定义中
    for other_id, other_c in concepts.items():
        if cid == other_id:
            continue
        other_name = other_c['name']
        # 如果其他概念名出现在本概念的定义中 → 依赖关系
        if other_name in def_text:
            add_edge(c['name'], other_name, '依赖')
        
        # 如果本概念名出现在其他概念的定义中 → 反向依赖
        if c['name'] in other_c['definition']:
            add_edge(c['name'], other_c['name'], '依赖')
    
    # 共享重要关键词的建立关联
    for other_id in range(cid + 1, max(concepts.keys()) + 1):
        if other_id not in concepts:
            continue
        other_c = concepts[other_id]
        other_def = other_c['definition']
        if not other_def:
            continue
        other_kws = set(re.findall(r'[\u4e00-\u9fff]{2,4}', other_def))
        shared_kws = def_kws & other_kws
        if len(shared_kws) >= 3:  # 共享3个以上关键词
            add_edge(c['name'], other_c['name'], '并列')

# ── 匹配3: 概念名子串匹配（A包含于B，或B包含于A）──
# 先建立概念名长度排序列表
name_sorted = sorted([(c['name'], cid) for cid, c in concepts.items()], key=lambda x: -len(x[0]))

print("\n基于概念名子串匹配...")
for i, (name_a, cid_a) in enumerate(name_sorted):
    for name_b, cid_b in name_sorted[i+1:]:
        # A是B的子串 → A是更基础的概念
        if name_a in name_b and name_a != name_b:
            # 短概念是长概念的基础 → 长概念依赖短概念
            # 但有些是包含关系，有些是并列
            # 短概念名在长概念名中 → 偏向"包含"关系（长包含短）
            add_edge(name_b, name_a, '包含')

# ── 匹配4: 共享knowledge_point的题目概念之间建立边 ──
# 如果两个概念共享相同的knowledge_point题目，它们相关
print("\n基于共享知识点匹配...")
kp_to_concepts = defaultdict(set)
for q in questions_raw:
    if q['concept_id'] and q['knowledge_point']:
        kp_to_concepts[q['knowledge_point']].add(q['concept_id'])

for kp, cids in kp_to_concepts.items():
    cids_list = list(cids)
    for i in range(len(cids_list)):
        for j in range(i+1, len(cids_list)):
            cid_a, cid_b = cids_list[i], cids_list[j]
            if cid_a in concepts and cid_b in concepts:
                add_edge(concepts[cid_a]['name'], concepts[cid_b]['name'], '并列')

# ── 匹配5: 原有的精确keyword_deps匹配 ──
keyword_deps = {
    '电路': ['电源', '导线', '电流', '电压', '电阻', '用电器'],
    '电流': ['电压', '电阻', '电源', '电路', '导体'],
    '电压': ['电流', '电源', '电阻', '电路'],
    '电阻': ['导体', '绝缘体', '电路', '电流'],
    '串联': ['电路', '电流', '电压', '电阻'],
    '并联': ['电路', '电流', '电压', '电阻'],
    '短路': ['电路', '电源', '导线', '电流'],
    '欧姆定律': ['电流', '电压', '电阻', '电路'],
    '电功率': ['电流', '电压', '电阻', '电能', '电路'],
    '电能': ['电路', '电流', '电压', '电源'],
    '电热': ['电流', '电阻', '电路'],
    '磁场': ['磁铁', '磁极', '磁力', '电流'],
    '电磁铁': ['磁场', '电流', '铁芯', '磁铁', '线圈'],
    '电磁感应': ['磁场', '磁铁', '线圈', '导体', '电流'],
    '发电机': ['电磁感应', '磁场', '线圈', '机械能'],
    '电动机': ['磁场', '电流', '线圈', '电能', '电磁铁'],
    '光的反射': ['光源', '光线', '光'],
    '光的折射': ['光源', '光线', '光', '介质'],
    '凸透镜': ['光', '折射', '焦点', '焦距'],
    '凹透镜': ['光', '折射', '焦点', '焦距'],
    '浮力': ['重力', '密度', '液体', '压力', '排开'],
    '压力': ['重力', '接触面', '受力面积'],
    '压强': ['压力', '受力面积'],
    '杠杆': ['支点', '力臂', '用力点', '阻力点'],
    '滑轮': ['杠杆', '绳子', '轮轴'],
    '定滑轮': ['滑轮', '杠杆', '绳子'],
    '动滑轮': ['滑轮', '杠杆', '绳子'],
    '轮轴': ['杠杆', '轮子', '轴'],
    '斜面': ['坡度', '高度', '长度'],
    '简单机械': ['杠杆', '滑轮', '轮轴', '斜面'],
    '能量': ['动能', '势能', '机械能', '电能', '热能'],
    '动能': ['质量', '速度', '运动'],
    '势能': ['高度', '弹性形变', '重力'],
    '机械能': ['动能', '势能'],
    '声音': ['振动', '声源', '介质', '耳'],
    '声音传播': ['声音', '介质', '振动'],
    '噪声': ['声音', '分贝'],
    '太阳系': ['太阳', '行星', '卫星', '地球'],
    '地球': ['太阳', '月球', '公转', '自转'],
    '月球': ['地球', '公转', '自转'],
    '日食': ['月球', '地球', '太阳', '公转'],
    '月食': ['地球', '月球', '太阳', '公转'],
    '月相': ['月球', '地球', '太阳', '公转'],
    '地球自转': ['地球', '地轴'],
    '地球公转': ['地球', '太阳', '自转'],
    '四季': ['地球公转', '地轴', '倾斜'],
    '昼夜': ['地球自转', '太阳'],
    '星座': ['恒星', '地球', '观测'],
    '星空': ['星座', '恒星', '地球'],
    '植物': ['细胞', '根', '茎', '叶', '花', '种子', '光合作用'],
    '光合作用': ['叶绿体', '叶', '光', '二氧化碳', '水'],
    '呼吸作用': ['细胞', '氧气', '二氧化碳', '线粒体'],
    '种子': ['胚', '胚芽', '胚根', '子叶'],
    '种子萌发': ['种子', '水', '空气', '温度'],
    '花': ['雄蕊', '雌蕊', '花粉', '传粉'],
    '传粉': ['花', '花粉', '雄蕊', '雌蕊'],
    '果实': ['花', '子房', '种子'],
    '根': ['土壤', '水分', '无机盐'],
    '茎': ['根', '叶', '导管'],
    '叶': ['茎', '光合作用', '蒸腾作用'],
    '蒸腾作用': ['叶', '气孔', '水'],
    '动物': ['细胞', '组织', '器官', '系统', '生物'],
    '人体': ['细胞', '组织', '器官', '系统', '消化', '呼吸', '循环'],
    '消化系统': ['口腔', '食道', '胃', '小肠', '大肠', '营养'],
    '呼吸系统': ['鼻', '咽', '喉', '气管', '肺', '支气管'],
    '循环系统': ['心脏', '血管', '血液'],
    '神经系统': ['脑', '脊髓', '神经'],
    '骨骼': ['骨', '关节', '肌肉'],
    '肌肉': ['骨骼', '收缩', '舒张'],
    '关节': ['骨', '肌肉', '韧带'],
    '食物': ['营养', '能量', '消化'],
    '营养': ['蛋白质', '糖类', '脂肪', '维生素', '矿物质'],
    '消化': ['营养', '消化系统', '酶'],
    '水的净化': ['沉淀', '过滤', '吸附', '蒸馏'],
    '过滤': ['漏斗', '滤纸', '烧杯', '玻璃棒'],
    '空气': ['氮气', '氧气', '二氧化碳', '稀有气体'],
    '氧气': ['空气', '燃烧', '氧化反应'],
    '二氧化碳': ['空气', '燃烧', '光合作用'],
    '燃烧': ['氧气', '可燃物', '着火点'],
    '溶液': ['溶质', '溶剂', '溶解'],
    '溶解': ['溶质', '溶剂', '溶液', '搅拌'],
    '物质': ['分子', '原子', '元素', '物质变化'],
    '分子': ['原子', '物质'],
    '原子': ['分子', '质子', '中子', '电子', '元素'],
    '元素': ['原子', '物质'],
    '混合物': ['纯净物'],
    '纯净物': ['元素', '化合物'],
    '化合物': ['元素', '纯净物'],
    '物理变化': ['物质', '分子'],
    '化学变化': ['物质', '分子', '原子', '新物质'],
    '金属': ['金属光泽', '导电性', '导热性', '延展性', '铁'],
    '铁': ['金属', '生锈', '磁铁'],
    '生锈': ['铁', '氧气', '水'],
    '生物': ['细胞', '生命', '生长', '繁殖'],
    '细胞': ['细胞膜', '细胞质', '细胞核', '细胞壁'],
    '微生物': ['细菌', '真菌', '病毒', '细胞'],
    '真菌': ['细胞', '孢子', '微生物'],
    '细菌': ['细胞', '微生物', '分裂'],
    '病毒': ['微生物', '遗传物质', '蛋白质'],
    '健康': ['营养', '运动', '休息', '卫生'],
    '环境保护': ['生态', '环境', '污染', '资源'],
    '生态': ['生物', '环境', '食物链', '生态系统'],
    '食物链': ['生态', '生物', '能量'],
    '天气': ['温度', '降水', '风', '云'],
    '气候': ['天气', '温度', '降水', '季节'],
    '化石': ['生物', '沉积', '地层', '古生物'],
    '遗传': ['基因', 'DNA', '染色体', '生物'],
    '变异': ['遗传', '基因', '生物', '进化'],
}

# 对每个概念，如果名称在keyword_deps中则建立精确匹配
for cid, c in concepts.items():
    name = c['name']
    # 精确匹配
    deps = keyword_deps.get(name, [])
    for dep_name in deps:
        if dep_name in concept_names_set:
            add_edge(name, dep_name, '依赖')
    
    # 模糊匹配：如果概念名包含keyword_deps中的key
    for key_name, dep_list in keyword_deps.items():
        if key_name in name and key_name != name:
            # 这个概念名包含已知关键词（如"电路基础"包含"电路"）
            for dep_name in dep_list:
                if dep_name in concept_names_set:
                    add_edge(name, dep_name, '依赖')

# ── 原有的包含关系 ──
contain_relations = {
    '电路': ['电源', '导线', '开关', '用电器'],
    '物质': ['纯净物', '混合物'],
    '纯净物': ['单质', '化合物'],
    '能量': ['电能', '热能', '光能', '声能', '动能', '势能', '机械能', '化学能', '核能'],
    '机械能': ['动能', '势能'],
    '势能': ['重力势能', '弹性势能'],
    '太阳系': ['太阳', '行星', '卫星', '小行星', '彗星'],
    '行星': ['水星', '金星', '地球', '火星', '木星', '土星', '天王星', '海王星'],
    '简单机械': ['杠杆', '滑轮', '轮轴', '斜面'],
    '滑轮': ['定滑轮', '动滑轮', '滑轮组'],
    '电磁铁': ['铁芯', '线圈'],
    '人体': ['消化系统', '呼吸系统', '循环系统', '神经系统', '运动系统'],
    '运动系统': ['骨骼', '肌肉', '关节'],
    '花': ['雄蕊', '雌蕊', '花瓣', '花萼', '花托', '花粉'],
    '种子': ['种皮', '胚', '胚芽', '胚根', '子叶'],
    '根': ['主根', '侧根', '根毛', '根尖'],
    '茎': ['节', '节间', '芽', '导管'],
    '叶': ['叶片', '叶柄', '叶脉', '气孔'],
    '细胞': ['细胞膜', '细胞质', '细胞核', '细胞壁', '叶绿体', '线粒体', '液泡'],
    '微生物': ['细菌', '真菌', '病毒'],
    '空气': ['氮气', '氧气', '二氧化碳', '稀有气体'],
    '溶液': ['溶质', '溶剂'],
    '消化系统': ['口腔', '食道', '胃', '小肠', '大肠', '肝', '胰'],
    '呼吸系统': ['鼻', '咽', '喉', '气管', '肺', '支气管'],
    '循环系统': ['心脏', '血管', '血液'],
    '神经系统': ['脑', '脊髓', '神经'],
    '水的净化': ['沉淀', '过滤', '吸附', '蒸馏'],
    '地球运动': ['地球自转', '地球公转'],
    '地球自转': ['昼夜交替'],
    '地球公转': ['四季变化', '昼夜长短'],
    '光': ['光源', '光线'],
    '透镜': ['凸透镜', '凹透镜'],
    '遗传': ['基因', 'DNA', '染色体'],
    '食物': ['蛋白质', '糖类', '脂肪', '维生素', '矿物质', '水'],
    '天气': ['气温', '降水', '风', '云量'],
}

for parent, children in contain_relations.items():
    # 精确匹配
    if parent in concept_names_set:
        for child in children:
            if child in concept_names_set:
                add_edge(parent, child, '包含')
    
    # 模糊匹配：如果概念名包含父概念名称
    for cid, c in concepts.items():
        name = c['name']
        if parent in name and name != parent:
            for child in children:
                if child in concept_names_set:
                    add_edge(name, child, '包含')

# ── 原有的并列关系 ──
coordinate_pairs = [
    ('串联', '并联'),
    ('导体', '绝缘体'),
    ('正极', '负极'),
    ('南极', '北极'),
    ('N极', 'S极'),
    ('凸透镜', '凹透镜'),
    ('光的反射', '光的折射'),
    ('定滑轮', '动滑轮'),
    ('动能', '势能'),
    ('物理变化', '化学变化'),
    ('混合物', '纯净物'),
    ('单质', '化合物'),
    ('溶质', '溶剂'),
    ('雄蕊', '雌蕊'),
    ('胚芽', '胚根'),
    ('主根', '侧根'),
    ('光合作用', '呼吸作用'),
    ('消化', '吸收'),
    ('动脉', '静脉'),
    ('吸气', '呼气'),
    ('收缩', '舒张'),
    ('蒸发', '沸腾'),
    ('溶解', '过滤'),
    ('沉淀', '过滤'),
    ('日食', '月食'),
    ('自转', '公转'),
    ('恒星', '行星'),
    ('地球自转', '地球公转'),
    ('噪声', '乐音'),
    ('天气', '气候'),
    ('分解反应', '化合反应'),
    ('氧化反应', '还原反应'),
    ('分子', '原子'),
    ('质子', '中子', '电子'),
    ('细菌', '真菌', '病毒'),
    ('根', '茎', '叶'),
    ('花', '果实', '种子'),
    ('骨骼', '肌肉', '关节'),
]

for pair in coordinate_pairs:
    for i in range(len(pair)):
        for j in range(i + 1, len(pair)):
            a, b = pair[i], pair[j]
            if a in concept_names_set and b in concept_names_set:
                add_edge(a, b, '并列')

# ═══ 第三步：组装输出 ═══

nodes = []
for cid in sorted(concepts.keys()):
    c = concepts[cid]
    nodes.append({
        "id": c['id'],
        "name": c['name'],
        "definition": c['definition'],
        "type": c['type_name'],
        "symbol": c['symbol'],
        "domain": c['domain'],
        "wrong_count": c['wrong_count'],
        "total_questions": c['total_questions'],
    })

output = {
    "nodes": nodes,
    "edges": edges,
}

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'concept_relations.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 已输出到 {out_path}")
print(f"\n══════ 统计信息 ══════")
print(f"节点数: {len(nodes)}")
print(f"边数: {len(edges)}")

rel_counts = {}
for e in edges:
    rel_counts[e['relation']] = rel_counts.get(e['relation'], 0) + 1
print(f"\n关系类型统计:")
for r, cnt in sorted(rel_counts.items(), key=lambda x: -x[1]):
    print(f"  {r}: {cnt}")

domain_counts = {}
for n in nodes:
    domain_counts[n['domain']] = domain_counts.get(n['domain'], 0) + 1
print(f"\nDomain 分布:")
for d, cnt in sorted(domain_counts.items(), key=lambda x: -x[1]):
    print(f"  {d}: {cnt}")

# 显示每个节点挂载了多少边
node_edge_counts = {}
for e in edges:
    for n in (e['source'], e['target']):
        node_edge_counts[n] = node_edge_counts.get(n, 0) + 1

print(f"\n孤立节点（无边）:")
isolated = [n['name'] for n in nodes if node_edge_counts.get(n['name'], 0) == 0]
if isolated:
    print(f"  共{len(isolated)}个: {', '.join(isolated[:20])}{'...' if len(isolated) > 20 else ''}")
else:
    print("  无")

min_edges = min(node_edge_counts.values()) if node_edge_counts else 0
max_edges = max(node_edge_counts.values())
avg_edges = sum(node_edge_counts.values()) / len(nodes) if nodes else 0
print(f"\n边统计:")
print(f"  最少: {min_edges}")
print(f"  最多: {max_edges}")
print(f"  平均: {avg_edges:.1f}")
