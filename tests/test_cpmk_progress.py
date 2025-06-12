import os
import unittest
from datetime import datetime

# Ensure required env variable is set before importing the app
os.environ["GEMINI_API_KEY"] = "dummy"

from app import app, db
from models import User, Classroom, CPMK, Quiz, SelfEvaluation, Assignment, AssignmentSubmission
from routes import calculate_cpmk_student_scores

class CPMKProgressTest(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["GEMINI_API_KEY"] = "dummy"
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True
        with app.app_context():
            db.create_all()
            teacher = User(email="t@example.com", role="teacher", first_name="T", last_name="Teach")
            teacher.set_password("pass")
            s1 = User(email="s1@example.com", role="student", first_name="S1", last_name="Stu")
            s1.set_password("pass")
            s2 = User(email="s2@example.com", role="student", first_name="S2", last_name="Stu")
            s2.set_password("pass")
            db.session.add_all([teacher, s1, s2])
            db.session.commit()
            classroom = Classroom(name="Class", description="", teacher_id=teacher.id)
            db.session.add(classroom)
            db.session.commit()
            cpmk = CPMK(code="C1", description="desc", classroom_id=classroom.id)
            db.session.add(cpmk)
            quiz = Quiz(
                title="q1",
                description="",
                teacher_id=teacher.id,
                classroom_id=classroom.id,
                quiz_type="mcq",
                questions_json="[]",
            )
            quiz.cpmks = [cpmk]
            assignment = Assignment(
                title="a1",
                classroom_id=classroom.id,
                teacher_id=teacher.id,
            )
            assignment.cpmks = [cpmk]
            db.session.add_all([quiz, assignment])
            db.session.commit()

            eval1 = SelfEvaluation(student_id=s1.id, classroom_id=classroom.id,
                                   quiz_id=quiz.id, quiz_type="mcq", questions_json="[]",
                                   answers_json="[]", score=80.0,
                                   completed_at=datetime.utcnow())
            eval2 = SelfEvaluation(student_id=s2.id, classroom_id=classroom.id,
                                   quiz_id=quiz.id, quiz_type="mcq", questions_json="[]",
                                   answers_json="[]", score=60.0,
                                   completed_at=datetime.utcnow())
            sub1 = AssignmentSubmission(assignment_id=assignment.id, student_id=s1.id,
                                       content="done", grade=90.0)
            sub2 = AssignmentSubmission(assignment_id=assignment.id, student_id=s2.id,
                                       content="done", grade=70.0)
            db.session.add_all([eval1, eval2, sub1, sub2])
            db.session.commit()

            self.cpmk_id = cpmk.id
            self.s1_id = s1.id
            self.s2_id = s2.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_student_progress_scores(self):
        with app.app_context():
            scores = calculate_cpmk_student_scores(self.cpmk_id)
            score_map = {s['student'].id: s['avg_score'] for s in scores}
            self.assertAlmostEqual(score_map[self.s1_id], 85.0)
            self.assertAlmostEqual(score_map[self.s2_id], 65.0)

if __name__ == '__main__':
    unittest.main()
