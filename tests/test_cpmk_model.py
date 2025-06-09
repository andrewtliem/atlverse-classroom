import os
import unittest
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
            cpmk = CPMK(code="C1", description="desc", classroom_id=self.classroom_id)
            db.session.add(cpmk)
            db.session.commit()
            material = Material(title="m1", classroom_id=self.classroom_id, cpmk_id=cpmk.id)
            quiz = Quiz(title="q1", description="", teacher_id=self.teacher_id, classroom_id=self.classroom_id, quiz_type="mcq", questions_json="[]", cpmk_id=cpmk.id)
            assignment = Assignment(title="a1", classroom_id=self.classroom_id, teacher_id=self.teacher_id, cpmk_id=cpmk.id)
            db.session.add_all([material, quiz, assignment])
            db.session.commit()
            self.assertEqual(material.cpmk.id, cpmk.id)
            self.assertEqual(quiz.cpmk.id, cpmk.id)
            self.assertEqual(assignment.cpmk.id, cpmk.id)

if __name__ == '__main__':
    unittest.main()
