"""
生成选择题选项（auto_choices.json）
为每道非选择题（填空/简答/判断/实验题等）自动生成4个选项
策略：
  1. 从同knowledge_point的其他题目的错误作答中提取干扰项
  2. 如果不够，从同concept_id的其他题目的错误作答中补充
  3. 仍然不够，用通用占位符
"""

import json, sqlite3, os
from collections import defaultdict

DB_PATH = r"C:\Users\HermesCC\baoke-science\baoke_learning.db"
OUTPUT = r"C:\Users\HermesCC\baoke-science\docs\auto_choices.json"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# ─── Load all data ───

questions = []
for r in conn.execute("""
    SELECT rq.*, sa.student_response, sa.is_correct
    FROM raw_questions rq
    LEFT JOIN student_answers sa ON rq.id = sa.question_id
    ORDER BY rq.id
""").fetchall():
    questions.append(dict(r))

# Also load ALL wrong answers grouped by knowledge_point and concept_id
wrong_by_kp = defaultdict(list)      # knowledge_point -> list of wrong responses
wrong_by_concept = defaultdict(list) # concept_id -> list of wrong responses

for r in conn.execute("""
    SELECT rq.id, rq.knowledge_point, rq.concept_id, sa.student_response
    FROM student_answers sa
    JOIN raw_questions rq ON sa.question_id = rq.id
    WHERE sa.is_correct = '✗' AND sa.student_response IS NOT NULL AND sa.student_response != ''
"""):
    d = dict(r)
    resp = d['student_response'].strip()
    if resp and resp not in ('（空白）', '未作答', '(空白）', ''):
        kp = d['knowledge_point']
        cid = d['concept_id']
        if kp:
            wrong_by_kp[kp].append(resp)
        if cid:
            wrong_by_concept[cid].append(resp)

# Get type name for each question
type_map = {}
for r in conn.execute("SELECT id, name FROM question_types").fetchall():
    type_map[r['id']] = r['name']

conn.close()

# ─── Generic distractors ───
GENERIC_DISTRACTORS = [
    "以上说法都不对",
    "以上说法都对",
    "无法确定",
    "与题意不符"
]

# ─── Helper: pick N distinct distractors from a list, excluding the correct answer ───
def pick_distractors(pool, correct_answer, n=3):
    """Pick up to n distractors from pool, excluding anything matching the correct answer."""
    result = []
    correct_lower = correct_answer.strip().lower() if correct_answer else ""
    for item in pool:
        if len(result) >= n:
            break
        item_clean = item.strip()
        if not item_clean:
            continue
        # Skip if it matches the correct answer
        if correct_lower and item_clean.strip().lower() == correct_lower:
            continue
        # Skip duplicates
        if item_clean in result:
            continue
        result.append(item_clean)
    return result

def generate_choices_for_all():
    """Generate choices for all questions."""
    auto_choices = {}
    
    # Track which questions already have options
    choice_count = 0
    
    for q in questions:
        qid = q['id']
        qtype_id = q['question_type_id']
        qtype_name = type_map.get(qtype_id, '未知')
        qtext = q['question_text'] or ''
        
        # Determine correct answer
        correct_answer = None
        
        # 1. Check correct_answer field
        if q['correct_answer'] and q['correct_answer'].strip():
            correct_answer = q['correct_answer'].strip()
        # 2. Fallback: from student_answers if marked correct
        elif q['student_response'] and q['is_correct'] == '✓':
            correct_answer = q['student_response'].strip()
        
        if not correct_answer:
            # No correct answer known — still generate placeholder options
            # Use the question's first concept-related wrong answer if available
            fallback_correct = None
            if cid and cid in wrong_by_concept:
                for wa in wrong_by_concept[cid]:
                    if wa.strip() and wa.strip() not in ('（空白）', '未作答', '(空白）', ''):
                        fallback_correct = wa.strip()[:60]
                        break
            if not fallback_correct and kp and kp in wrong_by_kp:
                for wa in wrong_by_kp[kp]:
                    if wa.strip() and wa.strip() not in ('（空白）', '未作答', '(空白）', ''):
                        fallback_correct = wa.strip()[:60]
                        break
            if not fallback_correct:
                fallback_correct = "正确答案"
            opts = [
                f"A. {fallback_correct}",
                "B. 常见错误",
                "C. 另一个可能",
                "D. 不正确的说法"
            ]
            auto_choices[str(qid)] = opts + [0]  # default: index 0 is correct
            continue
        
        # For 判断题: generate standard true/false style
        if qtype_name == '判断题':
            opts = [
                "A. 正确",
                "B. 错误",
                "C. 无法判断",
                "D. 以上都不对"
            ]
            # Determine which is correct
            correct_lower = correct_answer.strip().lower()
            if correct_lower in ('对', '正确', '✓', 'true', 't', '是', '对的'):
                correct_idx = 0
            elif correct_lower in ('错', '错误', '✗', 'false', 'f', '否', '不对', '错的'):
                correct_idx = 1
            else:
                correct_idx = 0
            auto_choices[str(qid)] = opts + [correct_idx]
            choice_count += 1
            continue
        
        # For 选择题 with existing options — keep them, convert to array format
        if qtype_name == '选择题' and q['options']:
            existing = q['options']
            if isinstance(existing, str):
                try:
                    existing_opts = json.loads(existing)
                except:
                    existing_opts = existing.split('\n')
            else:
                existing_opts = list(existing) if existing else []
            
            if isinstance(existing_opts, list) and len(existing_opts) >= 2:
                # Determine correct index
                if q['correct_answer']:
                    ca = q['correct_answer'].strip()
                    # Try to find matching option index
                    try:
                        correct_idx = int(ca)
                    except ValueError:
                        # Try matching by text
                        correct_idx = 0
                        for i, opt in enumerate(existing_opts):
                            if isinstance(opt, str) and ca.lower() in opt.lower():
                                correct_idx = i
                                break
                else:
                    correct_idx = 0
                # Ensure exactly 4 options
                while len(existing_opts) < 4:
                    existing_opts.append(GENERIC_DISTRACTORS[len(existing_opts) % len(GENERIC_DISTRACTORS)])
                auto_choices[str(qid)] = existing_opts[:4] + [correct_idx]
                choice_count += 1
                continue
        
        # For all other types (填空/简答/实验题等):
        kp = q['knowledge_point']
        cid = q['concept_id']
        
        # Build correct answer as an option
        correct_opt = correct_answer[:80]  # truncate long answers
        
        # If correct answer is a single letter (A/B/C/D) and we can find it in the wrong pool,
        # replace it with the actual text response from a wrong answer on a related concept
        # to make it more meaningful
        if correct_opt.strip() in ('A', 'B', 'C', 'D', 'E') and len(correct_opt.strip()) == 1:
            # Try to find a more descriptive correct answer from questions sharing this knowledge_point
            letter = correct_opt.strip()
            for other_q in questions:
                if other_q['id'] == qid:
                    continue
                if other_q.get('knowledge_point') == kp or other_q.get('concept_id') == cid:
                    sa = other_q.get('student_response', '')
                    if sa and sa.strip().startswith(letter + '.') or sa and sa.strip().startswith(letter + '）'):
                        correct_opt = sa.strip()[:80]
                        break
            # If still just a letter and we have correct_answer with full text in Q's options (JSON)
            if correct_opt.strip() in ('A', 'B', 'C', 'D', 'E') and q.get('raw_response_json'):
                try:
                    raw = json.loads(q['raw_response_json'])
                    if isinstance(raw, dict):
                        # Try various keys
                        for key in ['答案', '正确答案', 'correct', '正确选项']:
                            if key in raw:
                                val = raw[key]
                                if isinstance(val, str) and len(val) > 3:
                                    correct_opt = val[:80]
                                    break
                except:
                    pass
        
        # Gather candidate distractors
        distractors = []
        
        # Level 1: From same knowledge_point wrong answers
        if kp and kp in wrong_by_kp:
            distractors = pick_distractors(wrong_by_kp[kp], correct_answer, 3)
        
        # Level 2: From same concept_id
        if len(distractors) < 3 and cid and cid in wrong_by_concept:
            more = pick_distractors(wrong_by_concept[cid], correct_answer, 3 - len(distractors))
            distractors.extend(more)
        
        # Level 3: From any wrong answers in the same knowledge_point (include correct-looking ones)
        if len(distractors) < 3 and kp and kp in wrong_by_kp:
            # Try harder — less strict matching
            for item in wrong_by_kp[kp]:
                if len(distractors) >= 3:
                    break
                item_clean = item.strip()
                if not item_clean or item_clean in distractors:
                    continue
                distractors.append(item_clean)
        
        # Level 4: Generic fallback
        while len(distractors) < 3:
            idx = len(distractors) % len(GENERIC_DISTRACTORS)
            d = GENERIC_DISTRACTORS[idx]
            if d not in distractors:
                distractors.append(d)
            else:
                distractors.append(f"选项{chr(65 + len(distractors))}")
        
        # Shuffle: place correct answer at a random position among 4
        # First, shorten distractors if needed
        distractors = distractors[:3]
        
        # Construct final 4 options
        all_options = [correct_opt] + distractors
        # Assign labels
        labeled = []
        for i, opt in enumerate(all_options):
            labeled.append(f"{chr(65+i)}. {opt}")
        
        correct_idx = 0  # correct is index 0
        auto_choices[str(qid)] = labeled + [correct_idx]
        choice_count += 1
    
    # Save
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(auto_choices, f, ensure_ascii=False, indent=2)
    
    # Stats
    total = len(questions)
    with_choices = len(auto_choices)
    print(f"✅ 选项生成完成: {OUTPUT}")
    print(f"   总题目: {total}")
    print(f"   已生成选项: {with_choices}")
    
    # Check coverage
    type_counts = defaultdict(int)
    for q in questions:
        qid = str(q['id'])
        if qid in auto_choices:
            type_counts[type_map.get(q['question_type_id'], '未知')] += 1
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"   {t}: {c} 题有选项")
    
    return auto_choices

if __name__ == '__main__':
    generate_choices_for_all()
