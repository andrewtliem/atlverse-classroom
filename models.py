from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import string

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'teacher' or 'student'
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    taught_classrooms = db.relationship('Classroom', backref='teacher', lazy=True)
    enrollments = db.relationship('Enrollment', backref='student', lazy=True)
    self_evaluations = db.relationship('SelfEvaluation', backref='student', lazy=True)
    created_quizzes = db.relationship('Quiz', backref='teacher', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    invitation_code = db.Column(db.String(10), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    enrollments = db.relationship('Enrollment', backref='classroom', lazy=True, cascade='all, delete-orphan')
    materials = db.relationship('Material', backref='classroom', lazy=True, cascade='all, delete-orphan')
    self_evaluations = db.relationship('SelfEvaluation', backref='classroom', lazy=True, cascade='all, delete-orphan')
    quizzes = db.relationship('Quiz', backref='classroom', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(Classroom, self).__init__(**kwargs)
        if not self.invitation_code:
            self.invitation_code = self.generate_invitation_code()
    
    @staticmethod
    def generate_invitation_code():
        """Generate a unique 6-character invitation code"""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if not Classroom.query.filter_by(invitation_code=code).first():
                return code

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('classroom_id', 'student_id', name='unique_enrollment'),)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    file_path = db.Column(db.String(500))
    file_type = db.Column(db.String(50))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    self_evaluations = db.relationship('SelfEvaluation', backref='material', lazy=True)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    quiz_type = db.Column(db.String(20), nullable=False)  # 'mcq', 'true_false', 'essay'
    questions_json = db.Column(db.Text, nullable=False)
    time_limit_minutes = db.Column(db.Integer)  # NULL means no time limit
    passing_score = db.Column(db.Float, default=60.0)
    is_required = db.Column(db.Boolean, default=False)
    available_from = db.Column(db.DateTime)
    available_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published = db.Column(db.Boolean, default=False)
    max_attempts = db.Column(db.Integer) # NULL means unlimited attempts
    
    # Relationships
    evaluations = db.relationship('SelfEvaluation', backref='quiz', lazy=True)

    def is_available(self):
        """Check if the quiz is available for students to take"""
        now = datetime.utcnow()
        return (self.published and 
                (self.available_from is None or now >= self.available_from) and
                (self.available_until is None or now <= self.available_until))
    
    def is_upcoming(self):
        """Check if the quiz is published but not yet available"""
        now = datetime.utcnow()
        return self.published and self.available_from and now < self.available_from
    
    def is_expired(self):
        """Check if the quiz availability period has ended"""
        now = datetime.utcnow()
        return self.published and self.available_until and now > self.available_until

class SelfEvaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=True)
    quiz_type = db.Column(db.String(20), nullable=False)  # 'mcq', 'true_false', 'essay'
    questions_json = db.Column(db.Text, nullable=False)
    answers_json = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float)
    feedback_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    # Flag to distinguish between AI-generated and teacher-created quizzes
    is_ai_generated = db.Column(db.Boolean, default=True)
    # For timed quizzes, track when the student started
    started_at = db.Column(db.DateTime)
    
    def get_status(self):
        """Return the status of this evaluation"""
        if self.completed_at:
            return "completed"
        elif self.started_at:
            return "in_progress"
        else:
            return "not_started"
    
    def is_passed(self):
        """Check if the student passed the quiz based on its passing score"""
        if not self.completed_at or self.score is None:
            return False
            
        if self.quiz_id:
            # Use teacher-defined passing score for teacher quizzes
            passing_score = self.quiz.passing_score
        else:
            # Default passing score for AI-generated quizzes
            passing_score = 60.0
            
        return self.score >= passing_score
