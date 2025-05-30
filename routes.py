import os
import json
import defusedcsv as csv
import io
from datetime import datetime
from urllib.parse import urlparse, urljoin
from flask import render_template, request, redirect, url_for, flash, session, jsonify, send_file, make_response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from app import app, db
from models import User, Classroom, Enrollment, Material, SelfEvaluation, Quiz
from ai_service import AIService
from utils import allowed_file, extract_text_from_file

ai_service = AIService()

def is_safe_url(target):
    """Check if a URL is safe for redirect (same domain only)"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    return render_template('index.html')

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def auth_login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            else:
                return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def auth_register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        
        # Validation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('auth/register.html')
        
        if role not in ['teacher', 'student']:
            flash('Invalid role selected', 'error')
            return render_template('auth/register.html')
        
        # Create user
        user = User(
            email=email,
            role=role,
            first_name=first_name,
            last_name=last_name
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Registration successful!', 'success')
        return redirect(url_for('index'))
    
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def auth_logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# Teacher routes
@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get classrooms with quiz information
    classrooms = []
    for classroom in Classroom.query.filter_by(teacher_id=current_user.id).all():
        # Get quiz counts for this classroom
        quizzes = Quiz.query.filter_by(classroom_id=classroom.id).all()
        active_quizzes = [q for q in quizzes if q.published and q.is_available()]
        
        classroom.quiz_stats = {
            'total': len(quizzes),
            'published': len([q for q in quizzes if q.published]),
            'active': len(active_quizzes)
        }
        classrooms.append(classroom)
    
    return render_template('teacher/dashboard.html', classrooms=classrooms)

@app.route('/teacher/classroom/create', methods=['POST'])
@login_required
def teacher_create_classroom():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Classroom name is required', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    classroom = Classroom(
        name=name,
        description=description,
        teacher_id=current_user.id
    )
    
    db.session.add(classroom)
    db.session.commit()
    
    flash(f'Classroom "{name}" created successfully!', 'success')
    return redirect(url_for('teacher_classroom', classroom_id=classroom.id))

@app.route('/teacher/classroom/<int:classroom_id>')
@login_required
def teacher_classroom(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    materials = Material.query.filter_by(classroom_id=classroom_id).all()
    enrollments = Enrollment.query.filter_by(classroom_id=classroom_id).all()
    students = [enrollment.student for enrollment in enrollments]
    quizzes = Quiz.query.filter_by(classroom_id=classroom_id).order_by(Quiz.created_at.desc()).all()
    
    return render_template('teacher/classroom.html', 
                         classroom=classroom, 
                         materials=materials,
                         students=students,
                         quizzes=quizzes)

@app.route('/teacher/classroom/<int:classroom_id>/quizzes_tab')
@login_required
def teacher_quizzes_tab(classroom_id):
    """Helper route to show quizzes tab in classroom view"""
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    quizzes = Quiz.query.filter_by(classroom_id=classroom_id).order_by(Quiz.created_at.desc()).all()
    
    return render_template('teacher/classroom_quizzes_tab.html', 
                         classroom=classroom, 
                         quizzes=quizzes)

@app.route('/teacher/classroom/<int:classroom_id>/upload', methods=['POST'])
@login_required
def teacher_upload_material(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('teacher_classroom', classroom_id=classroom_id))
    
    file = request.files['file']
    title = request.form.get('title')
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('teacher_classroom', classroom_id=classroom_id))
    
    if not title:
        title = file.filename
    
    try:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Extract text content
            content = extract_text_from_file(file_path, file.filename)
            
            material = Material(
                classroom_id=classroom_id,
                title=title,
                content=content,
                file_path=filename,
                file_type=file.filename.split('.')[-1].lower()
            )
            
            db.session.add(material)
            db.session.commit()
            
            flash('Material uploaded successfully!', 'success')
        else:
            flash('Invalid file type. Please upload PDF or text files.', 'error')
    
    except RequestEntityTooLarge:
        flash('File too large. Maximum size is 16MB.', 'error')
    except Exception as e:
        flash(f'Error uploading file: {str(e)}', 'error')
    
    return redirect(url_for('teacher_classroom', classroom_id=classroom_id))

@app.route('/teacher/classroom/<int:classroom_id>/material/<int:material_id>/delete', methods=['POST'])
@login_required
def teacher_delete_material(classroom_id, material_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    material = Material.query.filter_by(id=material_id, classroom_id=classroom.id).first_or_404()

    try:
        # Delete the file from the server
        if material.file_path:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], material.file_path)
            if os.path.exists(file_path):
                os.remove(file_path)

        # Delete the material from the database
        db.session.delete(material)
        db.session.commit()
        flash(f'Material "{material.title}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting material: {str(e)}', 'error')

    return redirect(url_for('teacher_classroom', classroom_id=classroom_id))

@app.route('/teacher/classroom/<int:classroom_id>/student/<int:student_id>/remove', methods=['POST'])
@login_required
def teacher_remove_student(classroom_id, student_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    # Find the enrollment record for this student in this classroom
    enrollment = Enrollment.query.filter_by(classroom_id=classroom.id, student_id=student_id).first_or_404()
    student_user = User.query.get(student_id) # Get student user details for flash message

    try:
        db.session.delete(enrollment)
        db.session.commit()
        flash(f'{student_user.full_name} removed from the classroom.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error removing student: {str(e)}', 'error')

    return redirect(url_for('teacher_classroom', classroom_id=classroom_id))

@app.route('/teacher/classroom/<int:classroom_id>/add_student', methods=['POST'])
@login_required
def teacher_add_student(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    student_email = request.form.get('student_email')
    
    student = User.query.filter_by(email=student_email, role='student').first()
    if not student:
        flash('Student not found', 'error')
        return redirect(url_for('teacher_classroom', classroom_id=classroom_id))
    
    # Check if already enrolled
    existing_enrollment = Enrollment.query.filter_by(
        classroom_id=classroom_id,
        student_id=student.id
    ).first()
    
    if existing_enrollment:
        flash('Student is already enrolled in this classroom', 'warning')
        return redirect(url_for('teacher_classroom', classroom_id=classroom_id))
    
    enrollment = Enrollment(classroom_id=classroom_id, student_id=student.id)
    db.session.add(enrollment)
    db.session.commit()
    
    flash(f'Student {student.full_name} added successfully!', 'success')
    return redirect(url_for('teacher_classroom', classroom_id=classroom_id))

@app.route('/teacher/classroom/<int:classroom_id>/results')
@login_required
def teacher_results(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    evaluations = SelfEvaluation.query.filter_by(classroom_id=classroom_id).order_by(SelfEvaluation.created_at.desc()).all()
    
    # Create student summaries
    student_summaries = []
    students_data = {}
    
    # Group evaluations by student
    for evaluation in evaluations:
        student_id = evaluation.student_id
        if student_id not in students_data:
            students_data[student_id] = {
                'student': evaluation.student,
                'evaluations': [],
                'materials': set()
            }
        students_data[student_id]['evaluations'].append(evaluation)
        if evaluation.material_id:
            students_data[student_id]['materials'].add(evaluation.material_id)
    
    # Create summaries
    for student_id, data in students_data.items():
        evaluations_list = data['evaluations']
        completed_evals = [e for e in evaluations_list if e.completed_at and e.score is not None]
        
        summary = type('obj', (object,), {
            'student': data['student'],
            'total_evaluations': len(evaluations_list),
            'completed_count': len(completed_evals),
            'in_progress_count': len(evaluations_list) - len(completed_evals),
            'materials_attempted': len(data['materials']),
            'avg_score': sum(e.score for e in completed_evals) / len(completed_evals) if completed_evals else None
        })()
        student_summaries.append(summary)
    
    # Sort by student name
    student_summaries.sort(key=lambda x: x.student.full_name)
    
    return render_template('teacher/results.html', classroom=classroom, student_summaries=student_summaries, evaluations=evaluations)

@app.route('/teacher/classroom/<int:classroom_id>/student/<int:student_id>')
@login_required
def teacher_student_details(classroom_id, student_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    student = User.query.filter_by(id=student_id, role='student').first_or_404()
    
    # Get student's evaluations for this classroom
    evaluations = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id, 
        student_id=student_id
    ).order_by(SelfEvaluation.created_at.desc()).all()
    
    # Group evaluations by material
    materials_performance = {}
    for evaluation in evaluations:
        material_key = evaluation.material_id if evaluation.material_id else 'all_materials'
        material_title = evaluation.material.title if evaluation.material else 'All Materials'
        
        if material_key not in materials_performance:
            materials_performance[material_key] = {
                'material_title': material_title,
                'evaluations': []
            }
        materials_performance[material_key]['evaluations'].append(evaluation)
    
    return render_template('teacher/student_details.html', 
                         classroom=classroom, 
                         student=student, 
                         evaluations=evaluations,
                         materials_performance=materials_performance)

@app.route('/teacher/classroom/<int:classroom_id>/export_results')
@login_required
def teacher_export_results(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    evaluations = SelfEvaluation.query.filter_by(classroom_id=classroom_id).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Student Name', 'Student Email', 'Material', 'Quiz Type', 'Score', 'Date Completed'])
    
    # Write data
    for evaluation in evaluations:
        writer.writerow([
            evaluation.student.full_name,
            evaluation.student.email,
            evaluation.material.title if evaluation.material else 'General',
            evaluation.quiz_type.title(),
            f"{evaluation.score:.1f}%" if evaluation.score else 'Not scored',
            evaluation.completed_at.strftime('%Y-%m-%d %H:%M') if evaluation.completed_at else 'In progress'
        ])
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={classroom.name}_results.csv'
    
    return response

# Teacher Quiz Management routes
@app.route('/teacher/classroom/<int:classroom_id>/quizzes')
@login_required
def teacher_quizzes(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    quizzes = Quiz.query.filter_by(classroom_id=classroom_id).order_by(Quiz.created_at.desc()).all()
    
    return render_template('teacher/quizzes.html', 
                         classroom=classroom, 
                         quizzes=quizzes)

@app.route('/teacher/classroom/<int:classroom_id>/quiz/create', methods=['GET', 'POST'])
@login_required
def teacher_create_quiz(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        quiz_type = request.form.get('quiz_type')
        time_limit = request.form.get('time_limit')
        passing_score = request.form.get('passing_score')
        is_required = 'is_required' in request.form
        available_from = request.form.get('available_from')
        available_until = request.form.get('available_until')
        max_attempts = request.form.get('max_attempts')
        
        # Convert time limit to integer or None
        time_limit = int(time_limit) if time_limit and time_limit.isdigit() else None
        
        # Convert passing score to float
        try:
            passing_score = float(passing_score) if passing_score else 60.0
        except ValueError:
            passing_score = 60.0
        
        # Convert dates if provided
        from datetime import datetime
        available_from = datetime.fromisoformat(available_from) if available_from else None
        available_until = datetime.fromisoformat(available_until) if available_until else None
        
        # Convert max_attempts to integer or None
        try:
            max_attempts = int(max_attempts) if max_attempts else None
        except ValueError:
            max_attempts = None # Or handle as an error, but for now, treat invalid input as unlimited
        
        # Process questions
        questions = []
        question_count = int(request.form.get('question_count', 0))
        
        for i in range(question_count):
            question_text = request.form.get(f'question_{i}')
            
            if quiz_type == 'mcq':
                # Multiple choice question
                options = []
                for j in range(4):  # Assuming 4 options for MCQ
                    option = request.form.get(f'question_{i}_option_{j}')
                    if option:
                        options.append(f"{chr(65+j)}) {option}")
                
                correct_answer = request.form.get(f'question_{i}_correct')
                explanation = request.form.get(f'question_{i}_explanation', '')
                
                questions.append({
                    'question': question_text,
                    'options': options,
                    'correct_answer': correct_answer,
                    'explanation': explanation
                })
                
            elif quiz_type == 'true_false':
                # True/False question
                correct_answer = request.form.get(f'question_{i}_correct')
                explanation = request.form.get(f'question_{i}_explanation', '')
                
                questions.append({
                    'question': question_text,
                    'correct_answer': correct_answer,
                    'explanation': explanation
                })
                
            elif quiz_type == 'essay':
                # Essay question
                key_points = []
                key_points_count = int(request.form.get(f'question_{i}_key_points_count', 0))
                
                for j in range(key_points_count):
                    key_point = request.form.get(f'question_{i}_key_point_{j}')
                    if key_point:
                        key_points.append(key_point)
                
                suggested_length = request.form.get(f'question_{i}_suggested_length', '')
                
                questions.append({
                    'question': question_text,
                    'key_points': key_points,
                    'suggested_length': suggested_length
                })
        
        # Create quiz
        quiz = Quiz(
            title=title,
            description=description,
            teacher_id=current_user.id,
            classroom_id=classroom_id,
            quiz_type=quiz_type,
            questions_json=json.dumps(questions),
            time_limit_minutes=time_limit,
            passing_score=passing_score,
            is_required=is_required,
            available_from=available_from,
            available_until=available_until,
            published=False,  # Not published by default
            max_attempts=max_attempts
        )
        
        db.session.add(quiz)
        db.session.commit()
        
        flash('Quiz created successfully! Review and publish when ready.', 'success')
        return redirect(url_for('teacher_edit_quiz', quiz_id=quiz.id))
    
    return render_template('teacher/create_quiz.html', classroom=classroom)

@app.route('/teacher/quiz/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
def teacher_edit_quiz(quiz_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    quiz = Quiz.query.filter_by(id=quiz_id).first_or_404()
    # Check if the current teacher owns this quiz
    if quiz.teacher_id != current_user.id:
        flash('Access denied: you can only edit your own quizzes', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    classroom = quiz.classroom
    questions = json.loads(quiz.questions_json)
    
    # Add index to each question for easier access in template
    questions_with_index = []
    for i, question in enumerate(questions):
        question['index'] = i
        questions_with_index.append(question)

    if request.method == 'POST':
        quiz.title = request.form.get('title')
        quiz.description = request.form.get('description')
        quiz.time_limit_minutes = int(request.form.get('time_limit')) if request.form.get('time_limit') and request.form.get('time_limit').isdigit() else None
        quiz.passing_score = float(request.form.get('passing_score', 60.0))
        quiz.is_required = 'is_required' in request.form
        
        # Convert dates if provided
        available_from = request.form.get('available_from')
        available_until = request.form.get('available_until')
        max_attempts = request.form.get('max_attempts')
        
        from datetime import datetime
        quiz.available_from = datetime.fromisoformat(available_from) if available_from else None
        quiz.available_until = datetime.fromisoformat(available_until) if available_until else None
        
        # Convert max_attempts to integer or None
        try:
            quiz.max_attempts = int(max_attempts) if max_attempts else None
        except ValueError:
            quiz.max_attempts = None # Or handle as an error
        
        # Process questions (similar to create route)
        questions = []
        question_count = int(request.form.get('question_count', 0))
        
        for i in range(question_count):
            question_text = request.form.get(f'question_{i}')
            
            if quiz.quiz_type == 'mcq':
                options = []
                for j in range(4):
                    option = request.form.get(f'question_{i}_option_{j}')
                    if option:
                        options.append(f"{chr(65+j)}) {option}")
                
                correct_answer = request.form.get(f'question_{i}_correct')
                explanation = request.form.get(f'question_{i}_explanation', '')
                
                questions.append({
                    'question': question_text,
                    'options': options,
                    'correct_answer': correct_answer,
                    'explanation': explanation
                })
                
            elif quiz.quiz_type == 'true_false':
                correct_answer = request.form.get(f'question_{i}_correct')
                explanation = request.form.get(f'question_{i}_explanation', '')
                
                questions.append({
                    'question': question_text,
                    'correct_answer': correct_answer,
                    'explanation': explanation
                })
                
            elif quiz.quiz_type == 'essay':
                key_points = []
                key_points_count = int(request.form.get(f'question_{i}_key_points_count', 0))
                
                for j in range(key_points_count):
                    key_point = request.form.get(f'question_{i}_key_point_{j}')
                    if key_point:
                        key_points.append(key_point)
                
                suggested_length = request.form.get(f'question_{i}_suggested_length', '')
                
                questions.append({
                    'question': question_text,
                    'key_points': key_points,
                    'suggested_length': suggested_length
                })
        
        quiz.questions_json = json.dumps(questions)
        db.session.commit()
        
        flash('Quiz updated successfully!', 'success')
        return redirect(url_for('teacher_quizzes', classroom_id=classroom.id))
    
    return render_template('teacher/edit_quiz.html', 
                         classroom=classroom, 
                         quiz=quiz, 
                         questions=questions_with_index)

@app.route('/teacher/quiz/<int:quiz_id>/duplicate', methods=['POST'])
@login_required
def teacher_duplicate_quiz(quiz_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    original_quiz = Quiz.query.filter_by(id=quiz_id).first_or_404()
    
    # Check if the current teacher owns this quiz
    if original_quiz.teacher_id != current_user.id:
        flash('Access denied: you can only duplicate your own quizzes', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Create a new quiz based on the original
    new_quiz = Quiz(
        title=f"Copy of {original_quiz.title}",
        description=original_quiz.description,
        teacher_id=current_user.id,
        classroom_id=original_quiz.classroom_id,
        quiz_type=original_quiz.quiz_type,
        questions_json=original_quiz.questions_json,
        time_limit_minutes=original_quiz.time_limit_minutes,
        passing_score=original_quiz.passing_score,
        is_required=original_quiz.is_required,
        published=False,  # Always start unpublished
        max_attempts=original_quiz.max_attempts
    )
    
    db.session.add(new_quiz)
    db.session.commit()
    
    flash('Quiz duplicated successfully! You can now edit the copy.', 'success')
    return redirect(url_for('teacher_edit_quiz', quiz_id=new_quiz.id))

@app.route('/teacher/quiz/<int:quiz_id>/preview')
@login_required
def teacher_preview_quiz(quiz_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    quiz = Quiz.query.filter_by(id=quiz_id).first_or_404()
    
    # Check if the current teacher owns this quiz
    if quiz.teacher_id != current_user.id:
        flash('Access denied: you can only preview your own quizzes', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    questions = json.loads(quiz.questions_json)
    
    # Add index to each question for easier access in template
    questions_with_index = []
    for i, question in enumerate(questions):
        question['index'] = i
        questions_with_index.append(question)
    
    return render_template('teacher/preview_quiz.html', 
                         classroom=quiz.classroom,
                         quiz=quiz,
                         questions=questions_with_index)

@app.route('/teacher/quiz/<int:quiz_id>/publish', methods=['POST'])
@login_required
def teacher_publish_quiz(quiz_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    quiz = Quiz.query.filter_by(id=quiz_id).first_or_404()
    
    # Check if the current teacher owns this quiz
    if quiz.teacher_id != current_user.id:
        flash('Access denied: you can only publish your own quizzes', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Set published state
    quiz.published = not quiz.published  # Toggle publish state
    db.session.commit()
    
    if quiz.published:
        flash('Quiz published successfully! Students can now access it.', 'success')
    else:
        flash('Quiz unpublished. Students can no longer access it.', 'warning')
    
    return redirect(url_for('teacher_quizzes', classroom_id=quiz.classroom_id))

@app.route('/teacher/quiz/<int:quiz_id>/results')
@login_required
def teacher_quiz_results(quiz_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    quiz = Quiz.query.filter_by(id=quiz_id).first_or_404()
    
    # Check if the current teacher owns this quiz
    if quiz.teacher_id != current_user.id:
        flash('Access denied: you can only view results for your own quizzes', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Get all evaluations for this quiz
    evaluations = SelfEvaluation.query.filter_by(quiz_id=quiz_id).all()
    
    # Get enrollment data to show students who haven't taken the quiz
    enrollments = Enrollment.query.filter_by(classroom_id=quiz.classroom_id).all()
    students = [enrollment.student for enrollment in enrollments]
    
    # Calculate statistics based on the latest evaluation for each student
    completed_students = set()
    in_progress_students = set()
    latest_completed_evaluations = {}
    
    for evaluation in evaluations:
        if evaluation.student_id not in completed_students and evaluation.student_id not in in_progress_students:
            if evaluation.completed_at is not None:
                completed_students.add(evaluation.student_id)
            elif evaluation.started_at is not None:
                in_progress_students.add(evaluation.student_id)

        # Keep track of the latest completed evaluation for each student
        if evaluation.completed_at is not None:
            student_id = evaluation.student_id
            if student_id not in latest_completed_evaluations or evaluation.completed_at > latest_completed_evaluations[student_id].completed_at:
                latest_completed_evaluations[student_id] = evaluation

    completed_count = len(completed_students)
    in_progress_count = len(in_progress_students)
    not_started_count = len(students) - (completed_count + in_progress_count)
    
    if completed_count > 0:
        # Calculate average score based on the latest completed evaluation for each student
        # Ensure 0 scores are included
        completed_scores = [e.score for e in latest_completed_evaluations.values() if e.score is not None]
        if completed_scores:
            avg_score = sum(completed_scores) / completed_count
        else:
            avg_score = 0.0 # Handle case where all completed scores are None (shouldn't happen if 0% is 0.0)
        pass_count = sum(1 for e in evaluations if e.completed_at is not None and e.score is not None and e.score >= quiz.passing_score)
        pass_rate = (pass_count / completed_count) * 100 if completed_count > 0 else 0
    else:
        avg_score = None
        pass_rate = None
    
    return render_template('teacher/quiz_results.html',
                         classroom=quiz.classroom,
                         quiz=quiz,
                         evaluations=evaluations,
                         students=students,
                         completed_count=completed_count,
                         in_progress_count=in_progress_count,
                         not_started_count=not_started_count,
                         avg_score=avg_score,
                         pass_rate=pass_rate)

@app.route('/teacher/quiz/<int:quiz_id>/submission/<int:evaluation_id>')
@login_required
def teacher_view_submission(quiz_id, evaluation_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    quiz = Quiz.query.filter_by(id=quiz_id).first_or_404()
    
    # Check if the current teacher owns this quiz
    if quiz.teacher_id != current_user.id:
        flash('Access denied: you can only view submissions for your own quizzes', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    evaluation = SelfEvaluation.query.filter_by(id=evaluation_id, quiz_id=quiz_id).first_or_404()
    
    questions = json.loads(evaluation.questions_json)
    answers = json.loads(evaluation.answers_json)
    feedback = json.loads(evaluation.feedback_json) if evaluation.feedback_json else []
    
    return render_template('teacher/view_submission.html',
                         classroom=quiz.classroom,
                         quiz=quiz,
                         evaluation=evaluation,
                         student=evaluation.student,
                         questions=questions,
                         answers=answers,
                         feedback=feedback)

@app.route('/teacher/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
def teacher_delete_quiz(quiz_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    quiz = Quiz.query.filter_by(id=quiz_id).first_or_404()

    # Check if the current teacher owns this quiz
    if quiz.teacher_id != current_user.id:
        flash('Access denied: you can only delete your own quizzes', 'error')
        return redirect(url_for('teacher_dashboard'))

    # Check if the quiz is published
    if quiz.published:
        flash('Cannot delete a published quiz. Unpublish it first.', 'error')
        return redirect(url_for('teacher_quizzes', classroom_id=quiz.classroom_id))

    try:
        # Delete the quiz from the database
        db.session.delete(quiz)
        db.session.commit()
        flash(f'Quiz "{quiz.title}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting quiz: {str(e)}', 'error')

    return redirect(url_for('teacher_quizzes', classroom_id=quiz.classroom_id))

# Student routes
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get enrollments with quiz information
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    classrooms = []
    
    for enrollment in enrollments:
        classroom = enrollment.classroom
        # Get all published quizzes for this classroom
        all_published_quizzes = Quiz.query.filter(
            Quiz.classroom_id == classroom.id,
            Quiz.published == True
        ).filter(
            (Quiz.available_from.is_(None) | (Quiz.available_from <= datetime.utcnow())) &
            (Quiz.available_until.is_(None) | (Quiz.available_until >= datetime.utcnow()))
        ).all()
        
        # Prepare quizzes with status for the current student
        quizzes_with_status = []
        for quiz in all_published_quizzes:
            quiz_status = 'Available' # Default status

            # Check availability dates
            if quiz.is_upcoming():
                quiz_status = 'Upcoming'
            elif quiz.is_expired():
                quiz_status = 'Expired'
            else: # Within available dates (or no dates set)
                # Count completed attempts for the current student on this quiz
                completed_attempts_count = SelfEvaluation.query.filter(
                    SelfEvaluation.student_id == current_user.id,
                    SelfEvaluation.quiz_id == quiz.id,
                    SelfEvaluation.completed_at.isnot(None)
                ).count()

                # Check maximum attempts limit first
                if quiz.max_attempts is not None and completed_attempts_count >= quiz.max_attempts:
                    quiz_status = 'Attempts Used'
                else:
                    # Check if the student has completed it at least once, but still has attempts left or unlimited attempts
                    any_completed_attempt = SelfEvaluation.query.filter(
                        SelfEvaluation.student_id == current_user.id,
                        SelfEvaluation.quiz_id == quiz.id,
                        SelfEvaluation.completed_at.isnot(None)
                    ).first()
                    if any_completed_attempt:
                        # Student has completed at least one attempt, but can still take more
                        # We can keep the status as 'Available' or introduce a new status like 'Completed (Attempts Left)'
                        # Let's keep it 'Available' for now to allow taking the quiz again easily
                        quiz_status = 'Available' # Or 'Completed' if you want to visually indicate completion but allow more
                    else:
                        # Student has not started or completed any attempt
                        quiz_status = 'Available'

            quizzes_with_status.append({
                'quiz': quiz,
                'status': quiz_status
            })
        
        classroom.quizzes_with_status = quizzes_with_status

        # Recalculate stats based on all published quizzes for the dashboard cards
        total_published = len(all_published_quizzes)
        available_now = len([q for q in quizzes_with_status if q['status'] == 'Available'])
        completed_count_stat = SelfEvaluation.query.filter(
            SelfEvaluation.student_id == current_user.id,
            SelfEvaluation.classroom_id == classroom.id,
            SelfEvaluation.quiz_id.isnot(None),
            SelfEvaluation.completed_at.isnot(None)
        ).count()
        
        classroom.quiz_stats = {
            'total_published': total_published,
            'available_now': available_now,
            'completed': completed_count_stat,
            'pending': available_now # Add pending count
        }
        classrooms.append(classroom)
    
    return render_template('student/dashboard.html', classrooms=classrooms)

@app.route('/student/join_classroom', methods=['POST'])
@login_required
def student_join_classroom():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    invitation_code = request.form.get('invitation_code').upper()
    
    classroom = Classroom.query.filter_by(invitation_code=invitation_code).first()
    if not classroom:
        flash('Invalid invitation code', 'error')
        return redirect(url_for('student_dashboard'))
    
    # Check if already enrolled
    existing_enrollment = Enrollment.query.filter_by(
        classroom_id=classroom.id,
        student_id=current_user.id
    ).first()
    
    if existing_enrollment:
        flash('You are already enrolled in this classroom', 'warning')
        return redirect(url_for('student_dashboard'))
    
    enrollment = Enrollment(classroom_id=classroom.id, student_id=current_user.id)
    db.session.add(enrollment)
    db.session.commit()
    
    flash(f'Successfully joined "{classroom.name}"!', 'success')
    return redirect(url_for('student_classroom', classroom_id=classroom.id))

@app.route('/student/classroom/<int:classroom_id>')
@login_required
def student_classroom(classroom_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Check enrollment
    enrollment = Enrollment.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id
    ).first_or_404()
    
    classroom = enrollment.classroom
    materials = Material.query.filter_by(classroom_id=classroom_id).all()
    
    # Get recent completed evaluations only
    recent_evaluations = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id
    ).order_by(SelfEvaluation.started_at.desc()).limit(4).all()
    
    # Get any available teacher-created quizzes
    available_quizzes = Quiz.query.filter_by(
        classroom_id=classroom_id,
        published=True
    ).filter(
        (Quiz.available_from.is_(None) | (Quiz.available_from <= datetime.utcnow())) &
        (Quiz.available_until.is_(None) | (Quiz.available_until >= datetime.utcnow()))
    ).all()
    
    # Calculate student's average score for teacher-created quizzes in this classroom
    student_completed_quizzes = SelfEvaluation.query.filter(
        SelfEvaluation.student_id == current_user.id,
        SelfEvaluation.classroom_id == classroom_id,
        SelfEvaluation.quiz_id.isnot(None), # Only include teacher-created quizzes
        SelfEvaluation.completed_at.isnot(None)
    ).all()
    student_avg_score = sum(q.score for q in student_completed_quizzes) / len(student_completed_quizzes) if student_completed_quizzes else None

    # Calculate class average score for teacher-created quizzes in this classroom
    # This is the average of all completed teacher-created quiz scores by all students
    all_classroom_completed_quizzes = SelfEvaluation.query.filter(
        SelfEvaluation.classroom_id == classroom_id,
        SelfEvaluation.quiz_id.isnot(None), # Only include teacher-created quizzes
        SelfEvaluation.completed_at.isnot(None)
    ).all()
    class_avg_score = sum(q.score for q in all_classroom_completed_quizzes) / len(all_classroom_completed_quizzes) if all_classroom_completed_quizzes else None

    # Check which quizzes the student has already started or completed
    quiz_status = {}
    for quiz in available_quizzes:
        evaluation = SelfEvaluation.query.filter_by(
            student_id=current_user.id,
            quiz_id=quiz.id
        ).first()
        
        if evaluation:
            quiz_status[quiz.id] = evaluation.get_status()
        else:
            quiz_status[quiz.id] = "not_started"
    
    return render_template('student/classroom.html', 
                         classroom=classroom, 
                         materials=materials,
                         recent_evaluations=recent_evaluations,
                         available_quizzes=available_quizzes,
                         quiz_status=quiz_status,
                         student_avg_score=student_avg_score,
                         class_avg_score=class_avg_score)

@app.route('/student/classroom/<int:classroom_id>/generate_study_guide')
@login_required
def student_generate_study_guide(classroom_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Check enrollment
    enrollment = Enrollment.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id
    ).first_or_404()
    
    classroom = enrollment.classroom
    
    # Get optional material_id from query parameters
    material_id = request.args.get('material_id')

    content = ""
    context = f"Classroom: {classroom.name}"
    
    if material_id:
        # Generate study guide for a specific material
        material = Material.query.filter_by(id=material_id, classroom_id=classroom.id).first()
        if not material or not material.content:
            flash('Material not found or has no content.', 'error')
            return redirect(url_for('student_classroom', classroom_id=classroom_id))
        content = material.content
        context = f"Material: {material.title} from Classroom: {classroom.name}"
        study_guide_title = f"Study Guide for {material.title}"
    else:\
        # Generate study guide for all materials
        materials = Material.query.filter_by(classroom_id=classroom.id).all()
        if not materials:
            flash('No materials available for study guide generation', 'warning')
            return redirect(url_for('student_classroom', classroom_id=classroom_id))
        content = "\n\n".join([f"**{material.title}**\n{material.content}" for material in materials if material.content])
        study_guide_title = f"Study Guide for {classroom.name}"

    if not content.strip():
        flash('No content available from selected material(s) for study guide generation.', 'warning')
        return redirect(url_for('student_classroom', classroom_id=classroom_id))
    
    try:
        # Assuming ai_service.generate_study_guide returns a string with the HTML content
        study_guide_content = ai_service.generate_study_guide(content, context)

        # Remove markdown code block fences if present
        if study_guide_content.startswith('```html\n'):
            study_guide_content = study_guide_content[len('```html\n'):]
        if study_guide_content.endswith('```'):
            study_guide_content = study_guide_content[:-len('```')]

        # Pass the generated study guide to the template
        return render_template('student/study_guide.html', 
                             classroom=classroom, 
                             study_guide=study_guide_content,
                             study_guide_title=study_guide_title,
                             material_id=material_id)
    
    except Exception as e:
        import traceback
        print(f"Study guide generation error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error generating study guide: {str(e)}', 'error')
        return redirect(url_for('student_classroom', classroom_id=classroom_id))

@app.route('/student/classroom/<int:classroom_id>/create_quiz')
@login_required
def student_create_quiz(classroom_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Check enrollment
    enrollment = Enrollment.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id
    ).first_or_404()
    
    classroom = enrollment.classroom
    materials = Material.query.filter_by(classroom_id=classroom_id).all()
    quiz_type = request.args.get('type', 'mcq')
    material_id = request.args.get('material_id')
    
    if not materials:
        flash('No materials available for quiz generation', 'warning')
        return redirect(url_for('student_classroom', classroom_id=classroom_id))
    
    try:
        # Get content for quiz generation
        if material_id:
            material = Material.query.get(material_id)
            if material and material.classroom_id == classroom_id:
                content = material.content
                context = f"Material: {material.title}"
            else:
                flash('Invalid material selected', 'error')
                return redirect(url_for('student_classroom', classroom_id=classroom_id))
        else:
            # Use all materials
            content = "\n\n".join([f"**{material.title}**\n{material.content}" for material in materials if material.content])
            context = f"All materials from {classroom.name}"
            material_id = None
        
        questions = ai_service.generate_quiz(content, quiz_type, context)
        
        # Create self-evaluation record
        evaluation = SelfEvaluation(
            student_id=current_user.id,
            classroom_id=classroom_id,
            material_id=material_id,
            quiz_type=quiz_type,
            questions_json=json.dumps(questions),
            answers_json=json.dumps([])  # Empty answers initially
        )
        
        db.session.add(evaluation)
        db.session.commit()
        
        return render_template('student/quiz_new.html', 
                             classroom=classroom,
                             evaluation=evaluation,
                             questions=questions,
                             quiz_type=quiz_type)
    
    except Exception as e:
        import traceback
        print(f"Quiz generation error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error generating quiz: {str(e)}', 'error')
        return redirect(url_for('student_classroom', classroom_id=classroom_id))

@app.route('/student/submit_quiz/<int:evaluation_id>', methods=['POST'])
@login_required
def student_submit_quiz(evaluation_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    evaluation = SelfEvaluation.query.filter_by(
        id=evaluation_id,
        student_id=current_user.id
    ).first_or_404()
    
    # Get submitted answers
    answers = []
    questions = json.loads(evaluation.questions_json)
    
    for i, question in enumerate(questions):
        answer_key = f'answer_{i}'
        if evaluation.quiz_type == 'essay':
            answer = request.form.get(answer_key, '').strip()
        else:
            answer = request.form.get(answer_key)
        answers.append(answer)
    
    try:
        # Score the quiz using AI
        score, feedback = ai_service.score_quiz(questions, answers, evaluation.quiz_type)
        
        # Update evaluation
        evaluation.answers_json = json.dumps(answers)
        evaluation.score = score
        evaluation.feedback_json = json.dumps(feedback)
        evaluation.completed_at = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Quiz submitted! Your score: {score:.1f}%', 'success')
        return redirect(url_for('student_quiz_result', evaluation_id=evaluation_id))
    
    except Exception as e:
        flash(f'Error scoring quiz: {str(e)}', 'error')
        return redirect(url_for('student_classroom', classroom_id=evaluation.classroom_id))

@app.route('/student/quiz_result/<int:evaluation_id>')
@login_required
def student_quiz_result(evaluation_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    evaluation = SelfEvaluation.query.filter_by(
        id=evaluation_id,
        student_id=current_user.id
    ).first_or_404()
    
    if not evaluation.completed_at:
        flash('Quiz not completed yet', 'warning')
        return redirect(url_for('student_classroom', classroom_id=evaluation.classroom_id))
    
    questions = json.loads(evaluation.questions_json)
    answers = json.loads(evaluation.answers_json)
    feedback = json.loads(evaluation.feedback_json) if evaluation.feedback_json else []
    
    return render_template('student/quiz.html',
                         classroom=evaluation.classroom,
                         evaluation=evaluation,
                         questions=questions,
                         answers=answers,
                         feedback=feedback,
                         quiz_type=evaluation.quiz_type,
                         show_results=True)

@app.route('/student/classroom/<int:classroom_id>/quiz/<int:quiz_id>')
@login_required
def student_take_teacher_quiz(classroom_id, quiz_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Check enrollment
    enrollment = Enrollment.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id
    ).first_or_404()
    
    # Get the quiz
    quiz = Quiz.query.filter_by(id=quiz_id, classroom_id=classroom_id, published=True).first_or_404()
    
    # Count completed attempts for this student on this quiz
    completed_attempts_count = SelfEvaluation.query.filter_by(
        student_id=current_user.id,
        quiz_id=quiz.id
    ).filter(SelfEvaluation.completed_at.isnot(None)).count()

    # Check if the student has exceeded the maximum number of attempts
    if quiz.max_attempts is not None and completed_attempts_count >= quiz.max_attempts:
        flash(f'You have reached the maximum number of attempts ({quiz.max_attempts}) for this quiz.', 'warning')
        return redirect(url_for('student_classroom', classroom_id=classroom_id))

    # Check if the quiz is available
    if not quiz.is_available():
        if quiz.is_upcoming():
            flash('This quiz is not yet available', 'warning')
        elif quiz.is_expired():
            flash('This quiz is no longer available', 'warning')
        else:
            flash('This quiz is not available', 'warning')
        return redirect(url_for('student_classroom', classroom_id=classroom_id))
    
    # Check if the student has already completed this quiz
    existing_evaluation = SelfEvaluation.query.filter_by(
        student_id=current_user.id,
        quiz_id=quiz_id,
        completed_at=None # Keep this to find an ongoing attempt
    ).first()
    
    if existing_evaluation:
        # Continue existing attempt
        if not existing_evaluation.started_at:
            # Mark as started if not already
            existing_evaluation.started_at = datetime.utcnow()
            db.session.commit()
        
        questions = json.loads(existing_evaluation.questions_json)
        return render_template('student/quiz_new.html',
                             classroom=quiz.classroom,
                             evaluation=existing_evaluation,
                             questions=questions,
                             quiz=quiz,
                             quiz_type=quiz.quiz_type,
                             time_limit=quiz.time_limit_minutes,
                             started_at=existing_evaluation.started_at.isoformat() if existing_evaluation.started_at else None)
    
    # Create a new evaluation
    questions = json.loads(quiz.questions_json)
    
    # Add index to each question for easier access in template
    questions_with_index = []
    for i, question in enumerate(questions):
        question['index'] = i
        questions_with_index.append(question)
    
    evaluation = SelfEvaluation(
        student_id=current_user.id,
        classroom_id=classroom_id,
        quiz_id=quiz_id,
        quiz_type=quiz.quiz_type,
        questions_json=quiz.questions_json,
        answers_json=json.dumps([]),
        is_ai_generated=False,
        started_at=datetime.utcnow()
    )
    
    db.session.add(evaluation)
    db.session.commit()
    
    return render_template('student/quiz_new.html',
                         classroom=quiz.classroom,
                         evaluation=evaluation,
                         questions=questions_with_index,
                         quiz=quiz,
                         quiz_type=quiz.quiz_type,
                         time_limit=quiz.time_limit_minutes,
                         started_at=evaluation.started_at.isoformat())

@app.route('/student/submit_teacher_quiz/<int:evaluation_id>', methods=['POST'])
@login_required
def student_submit_teacher_quiz(evaluation_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    evaluation = SelfEvaluation.query.filter_by(
        id=evaluation_id,
        student_id=current_user.id,
        completed_at=None
    ).first_or_404()
    
    # Make sure this is a teacher-created quiz
    if not evaluation.quiz_id or evaluation.is_ai_generated:
        flash('Invalid quiz submission', 'error')
        return redirect(url_for('student_dashboard'))
    
    # Get submitted answers
    answers = []
    questions = json.loads(evaluation.questions_json)
    
    for i, question in enumerate(questions):
        answer_key = f'answer_{i}'
        if evaluation.quiz_type == 'essay':
            answer = request.form.get(answer_key, '').strip()
        else:
            answer = request.form.get(answer_key)
        answers.append(answer)
    
    # Score the quiz
    if evaluation.quiz_type == 'mcq' or evaluation.quiz_type == 'true_false':
        # For objective questions, we can score them directly
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
        
    elif evaluation.quiz_type == 'essay':
        # For essays, use AI to score
        score, feedback = ai_service.score_quiz(questions, answers, evaluation.quiz_type)
    
    # Update evaluation
    evaluation.answers_json = json.dumps(answers)
    evaluation.score = score
    evaluation.feedback_json = json.dumps(feedback)
    evaluation.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Quiz submitted! Your score: {score:.1f}%', 'success')
    return redirect(url_for('student_quiz_result', evaluation_id=evaluation_id))

@app.route('/student/classroom/<int:classroom_id>/all_activities')
@login_required
def student_all_activities(classroom_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    # Check enrollment
    enrollment = Enrollment.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id
    ).first_or_404()

    classroom = enrollment.classroom

    # Get all evaluations for this student in this classroom, ordered by recency
    all_evaluations = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id
    ).order_by(SelfEvaluation.started_at.desc()).all()

    return render_template('student/all_activities.html',
                           classroom=classroom,
                           evaluations=all_evaluations)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error_message='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error_message='An internal error occurred'), 500
