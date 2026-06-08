"""
宝科学习数据库工具模块 v2.0
Claude Code / Hermes 通用
"""
import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baoke_learning.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ═══ 写入 ═══

def register_source_material(title, file_path, file_type, page_count, material_type, course_id=None, exam_date=None, exam_name=None):
    """注册原始素材"""
    with get_conn() as conn:
        mt = conn.execute("SELECT id FROM material_types WHERE name=?", (material_type,)).fetchone()
        if not mt:
            c = conn.execute("INSERT INTO material_types (name) VALUES (?)", (material_type,))
            mt_id = c.lastrowid
        else:
            mt_id = mt['id']
        
        conn.execute('''INSERT OR REPLACE INTO source_materials 
            (title, file_path, file_type, page_count, material_type_id, course_id, exam_date, exam_name)
            VALUES (?,?,?,?,?,?,?,?)''',
            (title, file_path, file_type, page_count, mt_id, course_id or 1, exam_date, exam_name))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def add_source_page(material_id, page_number, image_path=None, ocr_text=None, ocr_method=None):
    """添加素材页面"""
    with get_conn() as conn:
        conn.execute('''INSERT OR REPLACE INTO source_pages 
            (material_id, page_number, image_path, ocr_text, ocr_method)
            VALUES (?,?,?,?,?)''',
            (material_id, page_number, image_path, ocr_text, ocr_method))
        conn.commit()

def insert_question(source_page_id, material_id, course_id, qnum, qtext, qtype,
                    options, correct_answer, difficulty, score, kp, tags=None, raw_json=None):
    """插入题目，自动关联题型"""
    with get_conn() as conn:
        qt = conn.execute("SELECT id FROM question_types WHERE name=?", (qtype,)).fetchone()
        qt_id = qt['id'] if qt else None
        
        conn.execute('''INSERT INTO raw_questions 
            (source_page_id, material_id, course_id, question_number, question_text,
             question_type_id, options, correct_answer, difficulty, score_value,
             knowledge_point, tags, raw_response_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (source_page_id, material_id, course_id, qnum, qtext,
             qt_id, options, correct_answer, difficulty, score, kp, tags, raw_json))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def record_answer(question_id, student_response, is_correct, error_cause=None,
                  error_detail=None, exam_strategy=None, answer_date=None,
                  time_spent=None, attempt_number=1, exam_session_id=None):
    """记录学生作答"""
    with get_conn() as conn:
        conn.execute('''INSERT INTO student_answers
            (question_id, student_id, attempt_number, student_response, is_correct,
             error_cause, error_detail, exam_strategy, answer_date, time_spent_seconds, exam_session_id)
            VALUES (?,1,?,?,?,?,?,?,?,?,?)''',
            (question_id, attempt_number, student_response, is_correct,
             error_cause, error_detail, exam_strategy, answer_date, time_spent, exam_session_id))
        conn.commit()

def add_concept(name, definition, concept_type, course_id=1, analogy=None,
                example=None, counter_example=None, unit=None, parent_id=None):
    """添加概念"""
    with get_conn() as conn:
        ct = conn.execute("SELECT id FROM concept_types WHERE name=?", (concept_type,)).fetchone()
        if ct:
            conn.execute('''INSERT OR REPLACE INTO concepts
                (name, definition, analogy, example, counter_example, concept_type_id, course_id, unit, parent_concept_id)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (name, definition, analogy, example, counter_example, ct['id'], course_id, unit, parent_id))
            conn.commit()

# ═══ 查询 ═══

def get_student():
    with get_conn() as conn:
        return dict(conn.execute("SELECT * FROM students WHERE id=1").fetchone())

def get_course():
    with get_conn() as conn:
        r = conn.execute('''SELECT c.*, s.name as subject, g.name as grade
            FROM courses c JOIN subjects s ON c.subject_id=s.id
            JOIN grade_levels g ON c.grade_level_id=g.id WHERE c.id=1''').fetchone()
        return dict(r)

def get_wrong_answers():
    """获取全部错题（含溯源信息）"""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute('''
            SELECT sa.*, rq.question_text, rq.question_number, rq.knowledge_point,
                   sp.page_number, sm.title as source_title, sm.file_path
            FROM student_answers sa
            JOIN raw_questions rq ON sa.question_id = rq.id
            JOIN source_pages sp ON rq.source_page_id = sp.id
            JOIN source_materials sm ON rq.material_id = sm.id
            WHERE sa.is_correct = '✗'
            ORDER BY rq.knowledge_point, sa.error_cause
        ''').fetchall()]

def get_kp_error_stats():
    """知识点错误统计（含错误原因分布）"""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute('''
            SELECT rq.knowledge_point,
                   COUNT(*) as total_errors,
                   sa.error_cause,
                   COUNT(*) as cause_count
            FROM student_answers sa
            JOIN raw_questions rq ON sa.question_id = rq.id
            WHERE sa.is_correct = '✗'
            GROUP BY rq.knowledge_point, sa.error_cause
            ORDER BY total_errors DESC
        ''').fetchall()]

def get_all_questions_with_answers():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute('''
            SELECT rq.*, sa.student_response, sa.is_correct, sa.error_cause,
                   sa.error_detail, sa.exam_strategy, sp.page_number,
                   sm.title as source_title
            FROM raw_questions rq
            LEFT JOIN student_answers sa ON rq.id = sa.question_id
            LEFT JOIN source_pages sp ON rq.source_page_id = sp.id
            LEFT JOIN source_materials sm ON rq.material_id = sm.id
            ORDER BY rq.id
        ''').fetchall()]

def get_question_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM raw_questions").fetchone()[0]

def get_wrong_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM student_answers WHERE is_correct='✗'").fetchone()[0]

def get_concept_type_stats():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute('''
            SELECT ct.name, ct.symbol, COUNT(sa.id) as error_count
            FROM student_answers sa
            JOIN raw_questions rq ON sa.question_id = rq.id
            JOIN concepts c ON rq.concept_id = c.id
            JOIN concept_types ct ON c.concept_type_id = ct.id
            WHERE sa.is_correct = '✗'
            GROUP BY ct.name
            ORDER BY error_count DESC
        ''').fetchall()]

# ═══ 迁移 ═══

def migrate_from_v1(v1_json_path, source_title='练习题', material_type='练习题'):
    """从旧版 vision_results.json 迁移到新库"""
    with open(v1_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 注册素材
    mid = register_source_material(source_title, '', 'pdf', len(data), material_type)
    
    count = 0
    for page_data in data:
        content = page_data.get('content', '')
        page_num = page_data.get('page', 0)
        content = content.replace('```json', '').replace('```', '').strip()
        
        # 添加页面
        add_source_page(mid, page_num, ocr_text=content, ocr_method='gemini_vision')
        
        # 获取页面ID
        with get_conn() as conn:
            sp = conn.execute("SELECT id FROM source_pages WHERE material_id=? AND page_number=?",
                            (mid, page_num)).fetchone()
        if not sp:
            continue
        sp_id = sp['id']
        
        try:
            questions = json.loads(content)
            for q in questions:
                qnum = q.get('题号', '')
                qtext = q.get('题目', '')
                correct = q.get('对错', '')
                kp = q.get('知识点', '')
                err = q.get('错误原因', '')
                strat = q.get('出题思路', '')
                ctype = q.get('概念类型', '')
                ans = q.get('学生作答', '')
                
                # 推断题型
                if 'A.' in qtext or 'B.' in qtext:
                    qtype = '选择题'
                elif '____' in qtext or '（  ）' in qtext:
                    qtype = '填空题'
                elif '判断' in qtext or '是否正确' in qtext:
                    qtype = '判断题'
                else:
                    qtype = '简答题'
                
                qid = insert_question(sp_id, mid, 1, qnum, qtext, qtype,
                                     None, None, 3, 1, kp, None,
                                     json.dumps(q, ensure_ascii=False))
                
                record_answer(qid, ans, correct, error_cause=err,
                            error_detail=err, exam_strategy=strat)
                
                # 添加概念
                if kp:
                    ct_map = {'核心': '核心概念', '常考': '常考概念', '易错': '易错概念', '边缘': '边缘概念'}
                    ct = ct_map.get(ctype, '常考概念')
                    add_concept(kp, '', ct)
                
                count += 1
        except json.JSONDecodeError:
            print(f"  Skip page {page_num}: invalid JSON")
    
    print(f"Migrated {count} questions from {v1_json_path}")

if __name__ == '__main__':
    student = get_student()
    course = get_course()
    print(f"学生: {student['name']} | {course['grade']}{course['subject']}")
    print(f"题目: {get_question_count()} | 错题: {get_wrong_count()}")
