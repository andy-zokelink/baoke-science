"""
从 baoke_learning.db 导出全量数据为 data.js
"""
import json, sqlite3

DB_PATH = r"C:\Users\HermesCC\baoke-science\baoke_learning.db"
OUTPUT = r"C:\Users\HermesCC\baoke-science\docs\data.js"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 1. 所有题目 + 学生作答
questions = []
for r in conn.execute("""
    SELECT rq.*, sa.student_response, sa.is_correct, sa.error_cause, sa.error_detail,
           sa.exam_strategy, sp.page_number, sm.title as source_title
    FROM raw_questions rq
    LEFT JOIN student_answers sa ON rq.id = sa.question_id
    LEFT JOIN source_pages sp ON rq.source_page_id = sp.id
    LEFT JOIN source_materials sm ON rq.material_id = sm.id
    ORDER BY rq.id
""").fetchall():
    d = dict(r)
    # convert datetime to string
    for k, v in d.items():
        if isinstance(v, bytes):
            d[k] = v.decode()
    questions.append(d)

# 2. 概念 + 类型
concepts = []
for r in conn.execute("""
    SELECT c.*, ct.name as type_name, ct.symbol, ct.priority
    FROM concepts c
    LEFT JOIN concept_types ct ON c.concept_type_id = ct.id
    ORDER BY ct.priority DESC, c.name
""").fetchall():
    concepts.append(dict(r))

# 3. 概念关系
relations = []
for r in conn.execute("SELECT * FROM concept_relations").fetchall():
    relations.append(dict(r))

# 4. 教材页面
source_pages = []
for r in conn.execute("""
    SELECT sp.*, sm.title as material_title
    FROM source_pages sp
    JOIN source_materials sm ON sp.material_id = sm.id
    ORDER BY sp.material_id, sp.page_number
""").fetchall():
    d = dict(r)
    # Try to parse OCR text
    try:
        d['parsed'] = json.loads(d['ocr_text']) if d['ocr_text'] else {}
    except:
        d['parsed'] = {}
    source_pages.append(d)

# 5. 错题统计
from db_utils_v2 import get_kp_error_stats, get_concept_type_stats, get_wrong_answers
kp_stats = get_kp_error_stats()
ct_stats = get_concept_type_stats()
wrong_answers = get_wrong_answers()

# 6. 学生信息
student = conn.execute("SELECT * FROM students WHERE id=1").fetchone()
course = conn.execute("""
    SELECT c.*, s.name as subject, g.name as grade
    FROM courses c JOIN subjects s ON c.subject_id=s.id
    JOIN grade_levels g ON c.grade_level_id=g.id WHERE c.id=1
""").fetchone()

conn.close()

data = {
    "student": dict(student) if student else {},
    "course": dict(course) if course else {},
    "questions": questions,
    "concepts": concepts,
    "relations": relations,
    "source_pages": source_pages,
    "stats": {
        "question_count": len(questions),
        "concept_count": len(concepts),
        "wrong_count": len([q for q in questions if q.get('is_correct') == '✗']),
        "kp_error_stats": [dict(r) for r in kp_stats] if kp_stats else [],
        "concept_type_stats": [dict(r) for r in ct_stats] if ct_stats else [],
        "wrong_answers": [dict(r) for r in wrong_answers] if wrong_answers else []
    }
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write("// 宝科科学备考 - 全量数据\n")
    f.write("const BAOKE_DATA = ")
    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    f.write(";\n")

print(f"数据导出完成: {OUTPUT}")
print(f"  题目: {len(questions)}")
print(f"  概念: {len(concepts)}")
print(f"  关系: {len(relations)}")
print(f"  教材页面: {len(source_pages)}")
print(f"  错题: {len([q for q in questions if q.get('is_correct') == '✗'])}")
