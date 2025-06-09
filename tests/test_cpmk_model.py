import os
import unittest
os.environ["GEMINI_API_KEY"] = "dummy"
from app import app, db
from models import User, Classroom, CPMK, Material, Quiz, Assignment

class CPMKModelTest(unittest.TestCase):
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

    def test_cpmk_associations(self):
        with app.app_context():
            c1 = CPMK(code="C1", description="desc", classroom_id=self.classroom_id)
            c2 = CPMK(code="C2", description="desc2", classroom_id=self.classroom_id)
            db.session.add_all([c1, c2])
            db.session.commit()
            material = Material(title="m1", classroom_id=self.classroom_id)
            material.cpmks = [c1, c2]
            quiz = Quiz(title="q1", description="", teacher_id=self.teacher_id, classroom_id=self.classroom_id, quiz_type="mcq", questions_json="[]")
            quiz.cpmks = [c1, c2]
            assignment = Assignment(title="a1", classroom_id=self.classroom_id, teacher_id=self.teacher_id)
            assignment.cpmks = [c1, c2]
            db.session.add_all([material, quiz, assignment])
            db.session.commit()
            self.assertEqual(set(material.cpmks), {c1, c2})
            self.assertEqual(set(quiz.cpmks), {c1, c2})
            self.assertEqual(set(assignment.cpmks), {c1, c2})

if __name__ == '__main__':
    unittest.main()
