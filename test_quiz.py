#!/usr/bin/env python3
"""
Test script for the Quiz Management functionality
"""

import os
import sys
import json
import random
import datetime
from datetime import timedelta
from app import app, db
from models import User, Classroom, Quiz, SelfEvaluation, Enrollment

# Configuration
TEST_TEACHER_EMAIL = "test_teacher@example.com"
TEST_STUDENT_EMAIL = "test_student@example.com"
TEST_PASSWORD = "password123"

def cleanup():
    """Remove test data if it exists"""
    with app.app_context():
        # Remove test teacher
        test_teacher = User.query.filter_by(email=TEST_TEACHER_EMAIL).first()
        if test_teacher:
            # Find classrooms created by this teacher
            classrooms = Classroom.query.filter_by(teacher_id=test_teacher.id).all()
            
            for classroom in classrooms:
                # Find quizzes in this classroom
                quizzes = Quiz.query.filter_by(classroom_id=classroom.id).all()
                for quiz in quizzes:
                    # Delete evaluations for this quiz
                    SelfEvaluation.query.filter_by(quiz_id=quiz.id).delete()
                    # Delete the quiz
                    db.session.delete(quiz)
                
                # Delete enrollments
                Enrollment.query.filter_by(classroom_id=classroom.id).delete()
                # Delete the classroom
                db.session.delete(classroom)
        
            # Delete the teacher
            db.session.delete(test_teacher)
        
        # Remove test student
        test_student = User.query.filter_by(email=TEST_STUDENT_EMAIL).first()
        if test_student:
            # Delete evaluations by this student
            SelfEvaluation.query.filter_by(student_id=test_student.id).delete()
            # Delete enrollments
            Enrollment.query.filter_by(student_id=test_student.id).delete()
            # Delete the student
            db.session.delete(test_student)
        
        db.session.commit()
        print("Cleaned up test data")

def create_test_users():
    """Create test teacher and student accounts"""
    with app.app_context():
        # Create teacher
        teacher = User(
            email=TEST_TEACHER_EMAIL,
            role='teacher',
            first_name='Test',
            last_name='Teacher'
        )
        teacher.set_password(TEST_PASSWORD)
        
        # Create student
        student = User(
            email=TEST_STUDENT_EMAIL,
            role='student',
            first_name='Test',
            last_name='Student'
        )
        student.set_password(TEST_PASSWORD)
        
        db.session.add(teacher)
        db.session.add(student)
        db.session.commit()
        
        print(f"Created test teacher (ID: {teacher.id}) and student (ID: {student.id})")
        return teacher, student

def create_test_classroom(teacher):
    """Create a test classroom for the teacher"""
    with app.app_context():
        classroom = Classroom(
            name="Test Quiz Classroom",
            description="A classroom for testing quiz functionality",
            teacher_id=teacher.id
        )
        
        db.session.add(classroom)
        db.session.commit()
        
        print(f"Created test classroom: {classroom.name} (ID: {classroom.id})")
        return classroom

def enroll_student(student, classroom):
    """Enroll the test student in the classroom"""
    with app.app_context():
        enrollment = Enrollment(
            student_id=student.id,
            classroom_id=classroom.id
        )
        
        db.session.add(enrollment)
        db.session.commit()
        
        print(f"Enrolled student {student.email} in classroom {classroom.name}")
        return enrollment

def create_mcq_quiz(teacher, classroom):
    """Create a multiple choice quiz"""
    with app.app_context():
        # Quiz metadata
        quiz = Quiz(
            title="Test MCQ Quiz",
            description="A multiple choice quiz for testing",
            teacher_id=teacher.id,
            classroom_id=classroom.id,
            quiz_type="mcq",
            time_limit_minutes=10,
            passing_score=70.0,
            is_required=True,
            available_from=datetime.datetime.utcnow(),
            available_until=datetime.datetime.utcnow() + timedelta(days=7),
            published=True
        )
        
        # Create quiz questions
        questions = [
            {
                "question": "What is the capital of France?",
                "options": ["A) London", "B) Paris", "C) Berlin", "D) Madrid"],
                "correct_answer": "B",
                "explanation": "Paris is the capital of France."
            },
            {
                "question": "Which planet is known as the Red Planet?",
                "options": ["A) Venus", "B) Earth", "C) Mars", "D) Jupiter"],
                "correct_answer": "C",
                "explanation": "Mars is known as the Red Planet due to its reddish appearance."
            },
            {
                "question": "What is 2 + 2?",
                "options": ["A) 3", "B) 4", "C) 5", "D) 6"],
                "correct_answer": "B",
                "explanation": "2 + 2 equals 4."
            }
        ]
        
        quiz.questions_json = json.dumps(questions)
        
        db.session.add(quiz)
        db.session.commit()
        
        print(f"Created MCQ quiz: {quiz.title} (ID: {quiz.id})")
        return quiz

def create_true_false_quiz(teacher, classroom):
    """Create a true/false quiz"""
    with app.app_context():
        # Quiz metadata
        quiz = Quiz(
            title="Test True/False Quiz",
            description="A true/false quiz for testing",
            teacher_id=teacher.id,
            classroom_id=classroom.id,
            quiz_type="true_false",
            time_limit_minutes=5,
            passing_score=60.0,
            is_required=False,
            available_from=datetime.datetime.utcnow(),
            available_until=None,  # No expiration
            published=True
        )
        
        # Create quiz questions
        questions = [
            {
                "question": "The Earth is flat.",
                "correct_answer": "False",
                "explanation": "The Earth is approximately spherical."
            },
            {
                "question": "Water boils at 100 degrees Celsius at sea level.",
                "correct_answer": "True",
                "explanation": "At standard atmospheric pressure, water boils at 100°C."
            },
            {
                "question": "Python is a programming language.",
                "correct_answer": "True",
                "explanation": "Python is indeed a popular programming language."
            }
        ]
        
        quiz.questions_json = json.dumps(questions)
        
        db.session.add(quiz)
        db.session.commit()
        
        print(f"Created True/False quiz: {quiz.title} (ID: {quiz.id})")
        return quiz

def create_essay_quiz(teacher, classroom):
    """Create an essay quiz"""
    with app.app_context():
        # Quiz metadata
        quiz = Quiz(
            title="Test Essay Quiz",
            description="An essay quiz for testing",
            teacher_id=teacher.id,
            classroom_id=classroom.id,
            quiz_type="essay",
            time_limit_minutes=None,  # No time limit
            passing_score=50.0,
            is_required=False,
            available_from=datetime.datetime.utcnow() + timedelta(days=1),  # Available tomorrow
            available_until=datetime.datetime.utcnow() + timedelta(days=14),  # For 2 weeks
            published=False  # Initially unpublished
        )
        
        # Create quiz questions
        questions = [
            {
                "question": "Explain the concept of object-oriented programming.",
                "key_points": [
                    "Classes and objects",
                    "Encapsulation",
                    "Inheritance",
                    "Polymorphism"
                ],
                "suggested_length": "2-3 paragraphs"
            },
            {
                "question": "Discuss the importance of sustainable development.",
                "key_points": [
                    "Environmental considerations",
                    "Economic factors",
                    "Social implications",
                    "Future generations"
                ],
                "suggested_length": "300-500 words"
            }
        ]
        
        quiz.questions_json = json.dumps(questions)
        
        db.session.add(quiz)
        db.session.commit()
        
        print(f"Created Essay quiz: {quiz.title} (ID: {quiz.id})")
        return quiz

def test_quiz_availability(quiz):
    """Test quiz availability based on published status and dates"""
    with app.app_context():
        quiz = Quiz.query.get(quiz.id)  # Refresh quiz from database
        
        print(f"\nTesting availability for quiz: {quiz.title}")
        print(f"Published: {quiz.published}")
        print(f"Available from: {quiz.available_from}")
        print(f"Available until: {quiz.available_until}")
        
        # Test is_available() method
        is_available = quiz.is_available()
        print(f"Is available: {is_available}")
        
        # Test is_upcoming() method
        is_upcoming = quiz.is_upcoming()
        print(f"Is upcoming: {is_upcoming}")
        
        # Test is_expired() method
        is_expired = quiz.is_expired()
        print(f"Is expired: {is_expired}")
        
        return is_available

def test_student_quiz_access(student, quiz):
    """Test if a student can access the quiz"""
    with app.app_context():
        # Check if quiz is available
        if not quiz.is_available():
            print(f"Quiz {quiz.title} is not available to students")
            return False
        
        # Create a self-evaluation record
        evaluation = SelfEvaluation(
            student_id=student.id,
            classroom_id=quiz.classroom_id,
            quiz_id=quiz.id,
            quiz_type=quiz.quiz_type,
            questions_json=quiz.questions_json,
            answers_json=json.dumps([]),
            is_ai_generated=False,
            started_at=datetime.datetime.utcnow()
        )
        
        db.session.add(evaluation)
        db.session.commit()
        
        print(f"Student started quiz: {quiz.title} (Evaluation ID: {evaluation.id})")
        return evaluation

def test_submit_mcq_quiz(evaluation):
    """Test submitting an MCQ quiz"""
    with app.app_context():
        evaluation = SelfEvaluation.query.get(evaluation.id)  # Refresh from DB
        
        # Get questions
        questions = json.loads(evaluation.questions_json)
        
        # Generate answers (some correct, some incorrect)
        answers = []
        for question in questions:
            # 70% chance of correct answer, 30% chance of random wrong answer
            if random.random() < 0.7:
                answers.append(question['correct_answer'])
            else:
                options = ['A', 'B', 'C', 'D']
                options.remove(question['correct_answer'])
                answers.append(random.choice(options))
        
        # Process answers
        correct_count = 0
        feedback = []
        
        for i, (question, answer) in enumerate(zip(questions, answers)):
            is_correct = answer == question.get('correct_answer')
            if is_correct:
                correct_count += 1
            
            feedback.append({
                'question_index': i,
                'is_correct': is_correct,
                'correct_answer': question.get('correct_answer'),
                'explanation': question.get('explanation', ''),
                'user_answer': answer
            })
        
        score = (correct_count / len(questions)) * 100 if questions else 0
        
        # Update evaluation
        evaluation.answers_json = json.dumps(answers)
        evaluation.score = score
        evaluation.feedback_json = json.dumps(feedback)
        evaluation.completed_at = datetime.datetime.utcnow()
        
        db.session.commit()
        
        print(f"Submitted MCQ quiz. Score: {score:.1f}%")
        print(f"Correct answers: {correct_count}/{len(questions)}")
        
        # Check if passed
        passed = evaluation.is_passed()
        print(f"Passed: {passed}")
        
        return evaluation

def test_quiz_management():
    """Test the complete quiz management workflow"""
    try:
        # Setup test data
        print("\n=== Setting up test environment ===")
        cleanup()  # Clean up any existing test data
        teacher, student = create_test_users()
        classroom = create_test_classroom(teacher)
        enrollment = enroll_student(student, classroom)
        
        # Create different types of quizzes
        print("\n=== Creating test quizzes ===")
        mcq_quiz = create_mcq_quiz(teacher, classroom)
        tf_quiz = create_true_false_quiz(teacher, classroom)
        essay_quiz = create_essay_quiz(teacher, classroom)
        
        # Test quiz availability
        print("\n=== Testing quiz availability ===")
        mcq_available = test_quiz_availability(mcq_quiz)
        tf_available = test_quiz_availability(tf_quiz)
        essay_available = test_quiz_availability(essay_quiz)
        
        # Test publishing an unpublished quiz
        print("\n=== Testing quiz publishing ===")
        with app.app_context():
            essay_quiz = Quiz.query.get(essay_quiz.id)
            essay_quiz.published = True
            db.session.commit()
            print(f"Published essay quiz: {essay_quiz.title}")
            
            # Check availability again
            essay_available = test_quiz_availability(essay_quiz)
        
        # Test student access to quizzes
        print("\n=== Testing student quiz access ===")
        if mcq_available:
            mcq_evaluation = test_student_quiz_access(student, mcq_quiz)
            
            # Test quiz submission
            print("\n=== Testing quiz submission ===")
            if mcq_evaluation:
                completed_evaluation = test_submit_mcq_quiz(mcq_evaluation)
                
                # Check quiz results
                print("\n=== Quiz results ===")
                with app.app_context():
                    student_evals = SelfEvaluation.query.filter_by(
                        student_id=student.id, 
                        classroom_id=classroom.id
                    ).all()
                    
                    print(f"Student has {len(student_evals)} evaluations in this classroom")
                    for eval in student_evals:
                        print(f"Evaluation ID: {eval.id}, Quiz: {eval.quiz.title if eval.quiz else 'N/A'}")
                        print(f"Score: {eval.score}, Completed: {eval.completed_at}")
        
        print("\n=== Test completed successfully ===")
        
    except Exception as e:
        print(f"Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up
        print("\n=== Cleaning up test data ===")
        cleanup()

if __name__ == "__main__":
    test_quiz_management()

