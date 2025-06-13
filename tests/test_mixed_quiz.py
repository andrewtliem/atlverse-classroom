import os
import unittest
from app import app, db
from models import User, Classroom, Quiz, SelfEvaluation
from ai_service import AIService
import json

os.environ["GEMINI_API_KEY"] = "dummy"

class MixedQuizTest(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True
        with app.app_context():
            db.create_all()
            teacher = User(email="t@example.com", role="teacher", first_name="T", last_name="Teach")
            teacher.set_password("pass")
            db.session.add(teacher)
            db.session.commit()
            classroom = Classroom(name="Class", description="", teacher_id=teacher.id)
            db.session.add(classroom)
            db.session.commit()
            self.teacher_id = teacher.id
            self.classroom_id = classroom.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_mixed_quiz_scoring(self):
        with app.app_context():
            questions = [
                {"type": "mcq", "question": "Q1", "options": ["A) a", "B) b"], "correct_answer": "A"},
                {"type": "true_false", "question": "Q2", "correct_answer": "True"}
            ]
            quiz = Quiz(title="Mix", description="", teacher_id=self.teacher_id, classroom_id=self.classroom_id,
                        quiz_type="mixed", questions_json=json.dumps(questions))
            db.session.add(quiz)
            db.session.commit()

            svc = AIService()
            score, feedback = svc.score_quiz(questions, ["A", "False"], "mixed")
            self.assertEqual(len(feedback), 2)
            self.assertLess(score, 100)

