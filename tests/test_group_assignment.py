import os
import json
import unittest

from app import app, db
from models import User, Classroom, Enrollment, Assignment, AssignmentSubmission

class GroupAssignmentTest(unittest.TestCase):
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
            db.session.add_all([
                Enrollment(classroom_id=classroom.id, student_id=s1.id),
                Enrollment(classroom_id=classroom.id, student_id=s2.id),
            ])
            assignment = Assignment(title="A1", classroom_id=classroom.id, teacher_id=teacher.id,
                                    allow_group_submission=True, published=True)
            db.session.add(assignment)
            db.session.commit()
            self.teacher_id = teacher.id
            self.student1_id = s1.id
            self.student2_id = s2.id
            self.classroom_id = classroom.id
            self.assignment_id = assignment.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_group_submission_visible_for_all_members(self):
        with app.app_context():
            sub = AssignmentSubmission(
                assignment_id=self.assignment_id,
                student_id=self.student1_id,
                content="done",
                group_member_ids=json.dumps([self.student1_id, self.student2_id])
            )
            db.session.add(sub)
            db.session.commit()

            submissions = AssignmentSubmission.query.filter_by(assignment_id=self.assignment_id).all()
            found_for_s2 = None
            for s in submissions:
                member_ids = json.loads(s.group_member_ids or "[]")
                if self.student2_id == s.student_id or self.student2_id in member_ids:
                    found_for_s2 = s
                    break
            self.assertIsNotNone(found_for_s2)
            self.assertEqual(found_for_s2.id, sub.id)

if __name__ == '__main__':
    unittest.main()
