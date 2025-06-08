import os
import json
import defusedcsv as csv
import io
from datetime import datetime
from urllib.parse import urlparse, urljoin
from flask import render_template, request, redirect, url_for, flash, session, jsonify, send_file, make_response, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from app import app, db
from models import User, Classroom, Enrollment, Material, SelfEvaluation, Quiz, Notification, Assignment, AssignmentSubmission
from awards_utils import calculate_awards_for_student, calculate_star_total, get_classroom_star_rankings
from ai_service import AIService
from utils import allowed_file, extract_text_from_file
from sqlalchemy.orm import joinedload

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
        if not user or not user.check_password(password):
            flash('Invalid email or password', 'error')
            return render_template('auth/login.html')

        login_user(user)
        next_page = request.args.get('next')
        if next_page and is_safe_url(next_page):
            return redirect(next_page)
        else:
            return redirect(url_for('index'))
    
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

        # Create user in the local database
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
        
        # Get assignment counts for this classroom
        assignments = Assignment.query.filter_by(classroom_id=classroom.id).all()
        active_assignments = [a for a in assignments if a.published and not a.is_past_deadline()]

        classroom.assignment_stats = {
            'total': len(assignments),
            'published': len([a for a in assignments if a.published]),
            'active': len(active_assignments)
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
    assignments = Assignment.query.filter_by(classroom_id=classroom_id).order_by(Assignment.created_at.desc()).all() # New: Fetch assignments
    
    return render_template('teacher/classroom.html', 
                         classroom=classroom, 
                         materials=materials,
                         students=students,
                         quizzes=quizzes,
                         assignments=assignments) # Pass assignments to template

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

            # Notify enrolled students of new material
            enrollments = Enrollment.query.filter_by(classroom_id=classroom_id).all()
            for enrollment in enrollments:
                notification = Notification(
                    user_id=enrollment.student_id,
                    message=f'New material available: {material.title}',
                    link=url_for('student_classroom', classroom_id=classroom_id)
                )
                db.session.add(notification)
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
    
    # Precalculate rankings for star totals
    # rankings, student_count = get_classroom_star_rankings(classroom_id)

    # Create summaries
    # Calculate gold medal count and rank for all students in this classroom
    classroom_enrollments = Enrollment.query.filter_by(classroom_id=classroom_id).all()
    student_gold_counts = []
    for class_enrollment in classroom_enrollments:
        student_awards = calculate_awards_for_student(classroom_id, class_enrollment.student_id) # AI Awards for this student in this classroom
        student_gold_count = sum(1 for award_info in student_awards.values() if award_info.get('award') == 'gold') if student_awards else 0
        student_gold_counts.append((class_enrollment.student_id, student_gold_count))

    # Sort by gold count descending
    student_gold_counts.sort(key=lambda x: x[1], reverse=True)

    # Determine ranks
    gold_rankings = {}
    last_gold_count = -1
    rank_counter = 0
    # Handle empty student_gold_counts list case
    if student_gold_counts:
        for rank_idx, (student_id, gold_count) in enumerate(student_gold_counts, start=1):
            if gold_count != last_gold_count:
                rank_counter = rank_idx
                last_gold_count = gold_count
            gold_rankings[student_id] = {'rank': rank_counter, 'gold_count': gold_count}

    # Create summaries
    for student_id, data in students_data.items():
        evaluations_list = data['evaluations']
        completed_evals = [e for e in evaluations_list if e.completed_at and e.score is not None]

        # Get gold medal count and rank for this student
        gold_info = gold_rankings.get(student_id, {'rank': len(student_gold_counts), 'gold_count': 0})

        summary = type('obj', (object,), {
            'student': data['student'],
            'total_evaluations': len(evaluations_list),
            'completed_count': len(completed_evals),
            'in_progress_count': len(evaluations_list) - len(completed_evals),
            'materials_attempted': len(data['materials']),
            'avg_score': sum(e.score for e in completed_evals) / len(completed_evals) if completed_evals else None,
            'gold_medal_count': gold_info['gold_count'], # Add gold count
            'gold_rank': gold_info['rank'], # Add gold rank
            'rank_out_of': len(student_gold_counts) # Total students in ranking
        })()
        student_summaries.append(summary)

    # Sort by student name (already done, keeping sort at the end)
    # student_summaries.sort(key=lambda x: x.student.full_name)

    return render_template('teacher/results.html', classroom=classroom, student_summaries=student_summaries, evaluations=evaluations)

@app.route('/teacher/classroom/<int:classroom_id>/student/<int:student_id>')
@login_required
def teacher_student_details(classroom_id, student_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    student = User.query.filter_by(id=student_id, role='student').first_or_404()
    
    # Get materials for this classroom (for filter dropdown)
    materials = Material.query.filter_by(classroom_id=classroom_id).order_by(Material.title).all()

    # Get selected material_id for filtering
    filter_material_id = request.args.get('material_id', type=int)
    
    # Get student's evaluations for this classroom, filtered by material if specified
    evaluations_query = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id, 
        student_id=student_id
    )

    if filter_material_id:
        # Filter by the specific material_id for both teacher quizzes and AI quizzes
        evaluations_query = evaluations_query.filter_by(material_id=filter_material_id)

    evaluations = evaluations_query.order_by(SelfEvaluation.created_at.desc()).all()
    
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
                         materials_performance=materials_performance,
                         materials=materials, # Pass materials to template for filter
                         filter_material_id=filter_material_id # Pass selected filter to template
                        )

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
    
    # Precompute star totals for each student
    rankings, _ = get_classroom_star_rankings(classroom_id)

    # Write header
    writer.writerow(['Student Name', 'Student Email', 'Material', 'Quiz Type', 'Score', 'Date Completed', 'Total Stars'])
    
    # Write data
    for evaluation in evaluations:
        writer.writerow([
            evaluation.student.full_name,
            evaluation.student.email,
            evaluation.material.title if evaluation.material else 'General',
            evaluation.quiz_type.title(),
            f"{evaluation.score:.1f}%" if evaluation.score else 'Not scored',
            evaluation.completed_at.strftime('%Y-%m-%d %H:%M') if evaluation.completed_at else 'In progress',
            rankings.get(evaluation.student_id, {}).get('star_total', 0)
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
    
    # Set published state and track previous value
    was_published = quiz.published
    quiz.published = not quiz.published  # Toggle publish state
    db.session.commit()

    if quiz.published and not was_published:
        # Notify enrolled students about the new quiz
        enrollments = Enrollment.query.filter_by(classroom_id=quiz.classroom_id).all()
        for enrollment in enrollments:
            notification = Notification(
                user_id=enrollment.student_id,
                message=f'New quiz available: {quiz.title}',
                link=url_for('student_classroom', classroom_id=quiz.classroom_id)
            )
            db.session.add(notification)
        db.session.commit()
        flash('Quiz published successfully! Students can now access it.', 'success')
    elif not quiz.published and was_published:
        flash('Quiz unpublished. Students can no longer access it.', 'warning')
    else:
        flash('Quiz publish state updated.', 'info')
    
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

        # Star totals and ranking for this student
        # Removing star total and ranking for classroom card as requested
        # awards = calculate_awards_for_student(classroom.id, current_user.id)
        # classroom.star_total = calculate_star_total(awards)
        # rankings, student_count = get_classroom_star_rankings(classroom.id)
        # classroom.rank = rankings.get(current_user.id, {}).get('rank', student_count)
        # classroom.num_students = student_count
        classrooms.append(classroom)
    
    # Calculate AI Quiz Awards and Gold Medal Count for each classroom, and rank
    ai_quiz_awards_for_current_user = {}
    for enrollment in enrollments:
         classroom = enrollment.classroom # Get the classroom object here
         user_awards = calculate_awards_for_student(classroom.id, current_user.id)
         if user_awards:
              ai_quiz_awards_for_current_user[classroom.id] = user_awards

         # Calculate gold medal count for this classroom for the current user
         gold_count = sum(1 for award_info in user_awards.values() if award_info.get('award') == 'gold') if user_awards else 0
         classroom.gold_medal_count = gold_count # Add gold count to the classroom object

         # Calculate ranking based on gold medals for this classroom
         classroom_enrollments = Enrollment.query.filter_by(classroom_id=classroom.id).all()
         student_gold_counts = []
         for class_enrollment in classroom_enrollments:
             student_awards = calculate_awards_for_student(classroom.id, class_enrollment.student_id) # Awards for this student in this classroom
             student_gold_count = sum(1 for award_info in student_awards.values() if award_info.get('award') == 'gold') if student_awards else 0
             student_gold_counts.append((class_enrollment.student_id, student_gold_count))

         # Sort by gold count descending
         student_gold_counts.sort(key=lambda x: x[1], reverse=True)

         # Determine rank for the current user
         current_user_rank = 0
         last_gold_count = -1
         rank_counter = 0
         # Handle empty student_gold_counts list case
         if student_gold_counts:
             for rank_idx, (student_id, gold_count) in enumerate(student_gold_counts, start=1):
                 if gold_count != last_gold_count:
                     rank_counter = rank_idx
                     last_gold_count = gold_count
                 if student_id == current_user.id:
                     current_user_rank = rank_counter
                     break # Found the current user's rank

         classroom.gold_rank = current_user_rank # Add rank to classroom object
         classroom.num_students_in_ranking = len(student_gold_counts) # Total students in ranking (including those with 0 golds)

         # Fetch published assignments for the classroom
         all_published_assignments = Assignment.query.filter(
             Assignment.classroom_id == classroom.id,
             Assignment.published == True
         ).all()
         classroom.assignments_with_status = []
         for assignment in all_published_assignments:
             assignment_status = assignment.get_status()
             classroom.assignments_with_status.append({
                 'assignment': assignment,
                 'status': assignment_status
             })

         # Update assignment stats for dashboard card
         total_assignments = len(all_published_assignments)
         active_assignments = len([a for a in classroom.assignments_with_status if a['status'] == 'Active'])
         classroom.assignment_stats = {
             'total_published': total_assignments,
             'active_now': active_assignments
         }

         # No need to append here again as it's already done in the outer loop
         # classrooms.append(classroom)
    
    # Need classroom names for the template
    classroom_names = {c.id: c.name for c in Classroom.query.all()}

    
    return render_template('student/dashboard.html', 
                           classrooms=classrooms,
                           ai_quiz_awards=ai_quiz_awards_for_current_user,
                           classroom_names=classroom_names)

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
    
    # Get any in-progress AI quiz for the current student in this classroom
    in_progress_ai_quiz = SelfEvaluation.query.filter_by(
        student_id=current_user.id,
        classroom_id=classroom_id,
        is_ai_generated=True,
        completed_at=None
    ).first()

    # Get recent completed AI quizzes (SelfEvaluation where is_ai_generated is True)
    recent_ai_quizzes = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id,
        is_ai_generated=True
    ).filter(SelfEvaluation.completed_at.isnot(None)).all()

    # Get recent completed Teacher quizzes (SelfEvaluation where quiz_id is not None and is_ai_generated is False)
    recent_teacher_quizzes = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id,
        is_ai_generated=False
    ).filter(SelfEvaluation.quiz_id.isnot(None), SelfEvaluation.completed_at.isnot(None)).all()

    # Get recent assignment submissions
    recent_assignment_submissions = AssignmentSubmission.query.filter_by(
        student_id=current_user.id,
        assignment_id=classroom_id # Corrected filter to classroom_id instead of undefined assignment.id
    ).order_by(AssignmentSubmission.submitted_at.desc()).all()

    # Combine all recent activities
    recent_activities = []
    for quiz in recent_ai_quizzes:
        quiz.activity_type = 'ai_quiz'
        recent_activities.append(quiz)
    for quiz in recent_teacher_quizzes:
        quiz.activity_type = 'teacher_quiz'
        recent_activities.append(quiz)
    for submission in recent_assignment_submissions:
        submission.activity_type = 'assignment_submission'
        recent_activities.append(submission)

    # Sort combined activities by their timestamp (completed_at or submitted_at)
    recent_activities.sort(key=lambda x: x.completed_at if hasattr(x, 'completed_at') else x.submitted_at, reverse=True)
    
    # Limit to top 4 or 5 recent activities
    recent_activities = recent_activities[:5]
    
    # Get any available teacher-created quizzes
    available_quizzes = Quiz.query.filter_by(
        classroom_id=classroom_id,
        published=True
    ).filter(
        (Quiz.available_from.is_(None) | (Quiz.available_from <= datetime.utcnow())) &
        (Quiz.available_until.is_(None) | (Quiz.available_until >= datetime.utcnow()))
    ).all()
    
    # Get assignments for this classroom and student
    classroom_assignments = Assignment.query.filter_by(
        classroom_id=classroom_id,
        published=True
    ).order_by(Assignment.deadline.asc()).all()

    assignments_with_submission_status = []
    for assignment in classroom_assignments:
        submission = AssignmentSubmission.query.filter_by(
            assignment_id=assignment.id,
            student_id=current_user.id
        ).first()
        assignments_with_submission_status.append({'assignment': assignment, 'submission': submission})

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

    # Calculate student's average score for AI-generated quizzes in this classroom (overall)
    student_completed_ai_quizzes = SelfEvaluation.query.filter(
        SelfEvaluation.student_id == current_user.id,
        SelfEvaluation.classroom_id == classroom_id,
        SelfEvaluation.is_ai_generated == True,
        SelfEvaluation.completed_at.isnot(None)
    ).all()
    student_ai_avg_score_overall = sum(q.score for q in student_completed_ai_quizzes) / len(student_completed_ai_quizzes) if student_completed_ai_quizzes else None

    # Calculate class average score for AI-generated quizzes in this classroom (overall)
    all_classroom_completed_ai_quizzes = SelfEvaluation.query.filter(
        SelfEvaluation.classroom_id == classroom_id,
        SelfEvaluation.is_ai_generated == True,
        SelfEvaluation.completed_at.isnot(None)
    ).all()

    # Group completed AI quizzes by material for per-material averages
    student_ai_performance_by_material = {}
    class_ai_performance_by_material = {}

    from collections import defaultdict
    student_ai_scores_by_material = defaultdict(list)
    class_ai_scores_by_material = defaultdict(list)

    for eval in student_completed_ai_quizzes:
        material_id = eval.material_id if eval.material_id else 0 # Use 0 for quizzes not linked to specific material
        if eval.score is not None:
            student_ai_scores_by_material[material_id].append(eval.score)

    for eval in all_classroom_completed_ai_quizzes:
        material_id = eval.material_id if eval.material_id else 0
        if eval.score is not None:
             class_ai_scores_by_material[material_id].append(eval.score)

    # Calculate averages per material
    for material_id, scores in student_ai_scores_by_material.items():
        if scores:
            student_ai_performance_by_material[material_id] = sum(scores) / len(scores)
        else:
            student_ai_performance_by_material[material_id] = None

    for material_id, scores in class_ai_scores_by_material.items():
        if scores:
            class_ai_performance_by_material[material_id] = sum(scores) / len(scores)
        else:
            class_ai_performance_by_material[material_id] = None

    # Need material titles for the template - fetch materials again or pass a dictionary
    # Let's pass a dictionary mapping material_id to title
    material_titles = {m.id: m.title for m in materials}
    material_titles[0] = "All Materials"

    # Calculate overall class AI average (correctly handling division by zero)
    class_ai_avg_score_overall = sum(q.score for q in all_classroom_completed_ai_quizzes) / len(all_classroom_completed_ai_quizzes) if all_classroom_completed_ai_quizzes else None

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
                         recent_evaluations=recent_activities,
                         available_quizzes=available_quizzes,
                         quiz_status=quiz_status,
                         student_avg_score=student_avg_score,
                         class_avg_score=class_avg_score,
                         in_progress_ai_quiz=in_progress_ai_quiz,
                         student_ai_avg_score_overall=student_ai_avg_score_overall,
                         class_ai_avg_score_overall=class_ai_avg_score_overall,
                         student_ai_performance_by_material=student_ai_performance_by_material,
                         class_ai_performance_by_material=class_ai_performance_by_material,
                         material_titles=material_titles,
                         assignments_with_submission_status=assignments_with_submission_status)

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
    
    # Check for existing incomplete AI quiz for this student in this classroom
    existing_ai_evaluation = SelfEvaluation.query.filter_by(
        student_id=current_user.id,
        classroom_id=classroom_id,
        is_ai_generated=True,
        completed_at=None
    ).first()

    if existing_ai_evaluation:
        flash('You have an unfinished AI quiz. Please complete it first.', 'warning')
        return redirect(url_for('student_quiz_result', evaluation_id=existing_ai_evaluation.id))

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
    
    # Check if the quiz is completed or in progress
    if not evaluation.completed_at:
        # If not completed, render the quiz taking page
        questions = json.loads(evaluation.questions_json)
        return render_template('student/quiz_new.html',
                             classroom=evaluation.classroom,
                             evaluation=evaluation,
                             questions=questions,
                             quiz_type=evaluation.quiz_type,
                             # Pass any other necessary data for taking the quiz, like time limit if applicable
                             time_limit=None, # AI quizzes don't currently have a time limit
                             started_at=evaluation.started_at.isoformat() if evaluation.started_at else datetime.utcnow().isoformat() # Ensure started_at is set or passed
                            )

    # If completed, show the results
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
    recent_ai_quizzes = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id,
        is_ai_generated=True
    ).filter(SelfEvaluation.completed_at.isnot(None)).all()

    recent_teacher_quizzes = SelfEvaluation.query.filter_by(
        classroom_id=classroom_id,
        student_id=current_user.id,
        is_ai_generated=False
    ).filter(SelfEvaluation.quiz_id.isnot(None), SelfEvaluation.completed_at.isnot(None)).all()

    recent_assignment_submissions = AssignmentSubmission.query.filter_by(
        student_id=current_user.id,
        assignment_id=classroom_id  # Filter by classroom_id
    ).order_by(AssignmentSubmission.submitted_at.desc()).all()

    # Combine all recent activities
    all_activities = []
    for quiz in recent_ai_quizzes:
        quiz.activity_type = 'ai_quiz'
        all_activities.append(quiz)
    for quiz in recent_teacher_quizzes:
        quiz.activity_type = 'teacher_quiz'
        all_activities.append(quiz)
    for submission in recent_assignment_submissions:
        submission.activity_type = 'assignment_submission'
        all_activities.append(submission)

    # Sort combined activities by their timestamp (completed_at or submitted_at)
    all_activities.sort(key=lambda x: x.completed_at if hasattr(x, 'completed_at') else x.submitted_at, reverse=True)

    return render_template('student/all_activities.html',
                           classroom=classroom,
                           evaluations=all_activities)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """Serve uploaded files securely."""
    # Optionally verify user authorization to access this file
    material = Material.query.filter_by(file_path=filename).first()
    if material:
        if current_user.role == 'teacher':
            # Teacher can access only materials from their own classrooms
            if material.classroom.teacher_id != current_user.id:
                flash('Access denied', 'error')
                return redirect(url_for('index'))
        elif current_user.role == 'student':
            # Student must be enrolled in the classroom of the material
            enrollment = Enrollment.query.filter_by(
                classroom_id=material.classroom_id,
                student_id=current_user.id
            ).first()
            if not enrollment:
                flash('Access denied', 'error')
                return redirect(url_for('index'))

    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        flash('File not found.', 'error')
        return redirect(url_for('index')) # Or a suitable error page

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error_message='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error_message='An internal error occurred'), 500

@app.route('/teacher/classroom/<int:classroom_id>/student/<int:student_id>/reset_password', methods=['POST'])
@login_required
def teacher_reset_student_password(classroom_id, student_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    student = User.query.filter_by(id=student_id, role='student').first_or_404()

    # Ensure the student is in this classroom
    enrollment = Enrollment.query.filter_by(classroom_id=classroom.id, student_id=student.id).first()
    if not enrollment:
        flash('Student is not in this classroom.', 'error')
        return redirect(url_for('teacher_classroom', classroom_id=classroom_id))

    try:
        # Set the new password to '12345'
        new_password = '12345'

        # Set the new password
        student.set_password(new_password)
        db.session.commit()

        flash(f'Password for {student.full_name} reset successfully to: {new_password}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error resetting password: {str(e)}', 'error')

    return redirect(url_for('teacher_classroom', classroom_id=classroom_id))

@app.route('/teacher/edit_profile', methods=['GET', 'POST'])
@login_required
def teacher_edit_profile():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('teacher_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')

    return render_template('teacher/edit_profile.html', teacher=current_user)

@app.route('/teacher/change_password', methods=['GET', 'POST'])
@login_required
def teacher_change_password():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('Incorrect current password', 'error')
            return render_template('teacher/change_password.html')

        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return render_template('teacher/change_password.html')

        current_user.set_password(new_password)
        try:
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('teacher_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'error')

    return render_template('teacher/change_password.html')

@app.route('/student/edit_profile', methods=['GET', 'POST'])
@login_required
def student_edit_profile():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('student_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')

    return render_template('student/edit_profile.html', student=current_user)

@app.route('/student/change_password', methods=['GET', 'POST'])
@login_required
def student_change_password():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Check if current password is correct
        if not current_user.check_password(current_password):
            flash('Incorrect current password', 'error')
            return render_template('student/change_password.html')

        # Check if new password and confirm password match
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return render_template('student/change_password.html')

        # Update password
        current_user.set_password(new_password)
        try:
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('student_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'error')

    return render_template('student/change_password.html')


@app.route('/notifications', methods=['GET', 'POST'])
@login_required
def notifications():
    from models import Notification
    if request.method == 'POST':
        notif_id = request.form.get('notification_id')
        notification = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
        notification.is_read = True
        db.session.commit()
        return redirect(url_for('notifications'))

    notifications_list = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    return render_template('notifications.html', notifications=notifications_list)

@app.route('/teacher/classroom/<int:classroom_id>/assignments')
@login_required
def teacher_assignments(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    assignments = Assignment.query.filter_by(classroom_id=classroom_id).order_by(Assignment.created_at.desc()).all()
    
    return render_template('teacher/assignments.html', 
                         classroom=classroom, 
                         assignments=assignments)

@app.route('/teacher/classroom/<int:classroom_id>/assignment/create', methods=['GET', 'POST'])
@login_required
def teacher_create_assignment(classroom_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        deadline_str = request.form.get('deadline')
        published = 'published' in request.form

        if not title:
            flash('Assignment title is required.', 'error')
            return redirect(url_for('teacher_create_assignment', classroom_id=classroom.id))

        deadline = None
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('Invalid deadline format. Please use YYYY-MM-DDTHH:MM.', 'error')
                return redirect(url_for('teacher_create_assignment', classroom_id=classroom.id))

        assignment = Assignment(
            title=title,
            description=description,
            classroom_id=classroom.id,
            teacher_id=current_user.id,
            deadline=deadline,
            published=published
        )
        db.session.add(assignment)
        db.session.commit()

        # Notify students if published
        if published:
            for enrollment in classroom.enrollments:
                message = f'New assignment "{assignment.title}" posted in {classroom.name}. Deadline: {assignment.deadline.strftime("%Y-%m-%d %H:%M") if assignment.deadline else "N/A"}'
                notification = Notification(user_id=enrollment.student.id, message=message, link=url_for('student_view_assignment', assignment_id=assignment.id))
                db.session.add(notification)
            db.session.commit()

        flash(f'Assignment "{assignment.title}" created successfully!', 'success')
        return redirect(url_for('teacher_assignments', classroom_id=classroom.id))
    
    return render_template('teacher/create_assignment.html', classroom=classroom)

@app.route('/teacher/assignment/<int:assignment_id>/edit', methods=['GET', 'POST'])
@login_required
def teacher_edit_assignment(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    assignment = Assignment.query.filter_by(id=assignment_id, teacher_id=current_user.id).first_or_404()
    classroom = assignment.classroom

    if request.method == 'POST':
        assignment.title = request.form.get('title')
        assignment.description = request.form.get('description')
        deadline_str = request.form.get('deadline')
        assignment.published = 'published' in request.form

        if not assignment.title:
            flash('Assignment title is required.', 'error')
            return redirect(url_for('teacher_edit_assignment', assignment_id=assignment.id))

        assignment.deadline = None
        if deadline_str:
            try:
                assignment.deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('Invalid deadline format. Please use YYYY-MM-DDTHH:MM.', 'error')
                return redirect(url_for('teacher_edit_assignment', assignment_id=assignment.id))
        
        db.session.commit()
        flash(f'Assignment "{assignment.title}" updated successfully!', 'success')
        return redirect(url_for('teacher_assignments', classroom_id=classroom.id))

    return render_template('teacher/edit_assignment.html', assignment=assignment, classroom=classroom)

@app.route('/teacher/assignment/<int:assignment_id>/publish', methods=['POST'])
@login_required
def teacher_publish_assignment(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    assignment = Assignment.query.filter_by(id=assignment_id, teacher_id=current_user.id).first_or_404()
    classroom = assignment.classroom

    assignment.published = not assignment.published
    db.session.commit()

    if assignment.published:
        flash(f'Assignment "{assignment.title}" published successfully!', 'success')
        # Notify students upon publishing
        for enrollment in classroom.enrollments:
            message = f'New assignment "{assignment.title}" posted in {classroom.name}. Deadline: {assignment.deadline.strftime("%Y-%m-%d %H:%M") if assignment.deadline else "N/A"}'
            notification = Notification(user_id=enrollment.student.id, message=message, link=url_for('student_view_assignment', assignment_id=assignment.id))
            db.session.add(notification)
        db.session.commit()
    else:
        flash(f'Assignment "{assignment.title}" unpublished.', 'info')

    return redirect(url_for('teacher_assignments', classroom_id=classroom.id))

@app.route('/teacher/assignment/<int:assignment_id>/delete', methods=['POST'])
@login_required
def teacher_delete_assignment(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    assignment = Assignment.query.filter_by(id=assignment_id, teacher_id=current_user.id).first_or_404()
    classroom_id = assignment.classroom_id

    db.session.delete(assignment)
    db.session.commit()
    flash(f'Assignment "{assignment.title}" deleted successfully.', 'success')
    return redirect(url_for('teacher_assignments', classroom_id=classroom_id))

@app.route('/student/classroom/<int:classroom_id>/assignments')
@login_required
def student_assignments(classroom_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    classroom = Classroom.query.filter_by(id=classroom_id).first_or_404()
    if not Enrollment.query.filter_by(classroom_id=classroom.id, student_id=current_user.id).first():
        flash('You are not enrolled in this classroom.', 'error')
        return redirect(url_for('student_dashboard'))
    
    assignments = Assignment.query.filter_by(classroom_id=classroom_id).order_by(Assignment.created_at.desc()).all()

    # Fetch submission for each assignment for the current student
    assignments_with_submissions = []
    for assignment in assignments:
        submission = AssignmentSubmission.query.filter_by(assignment_id=assignment.id, student_id=current_user.id).first()
        assignments_with_submissions.append({'assignment': assignment, 'submission': submission})

    return render_template('student/assignments.html',
                           classroom=classroom,
                           assignments_with_submissions=assignments_with_submissions)

@app.route('/student/assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def student_view_assignment(assignment_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    assignment = Assignment.query.get_or_404(assignment_id)
    if not assignment.published:
        flash('Assignment not published.', 'error')
        return redirect(url_for('student_classroom', classroom_id=assignment.classroom_id))

    # Check for existing submission
    submission = AssignmentSubmission.query.filter_by(
        assignment_id=assignment.id,
        student_id=current_user.id
    ).first()

    # Determine if resubmission is allowed
    can_resubmit = False
    if submission: # If there's an existing submission
        # Resubmission is allowed if teacher explicitly allowed it AND it's before deadline
        if submission.is_resubmission_allowed and not assignment.is_past_deadline():
            can_resubmit = True
    else: # If no submission yet, it's a new submission, allowed if before deadline
        if not assignment.is_past_deadline():
            can_resubmit = True

    if request.method == 'POST':
        content = request.form.get('content')
        if not content:
            flash('Submission content cannot be empty.', 'error')
            return redirect(url_for('student_view_assignment', assignment_id=assignment.id))

        if submission: # Existing submission, so it's a resubmission
            if not can_resubmit:
                flash('Resubmission not allowed at this time.', 'error')
                return redirect(url_for('student_view_assignment', assignment_id=assignment.id))
            
            submission.content = content
            submission.submitted_at = datetime.utcnow()
            submission.status = 'Resubmitted'
            submission.grade = None # Clear grade on resubmission
            submission.feedback = None # Clear feedback on resubmission
            submission.is_resubmission_allowed = False # Teacher must re-enable if another resubmission is desired
            db.session.commit()
            flash('Assignment resubmitted successfully!', 'success')
        else: # New submission
            if assignment.is_past_deadline():
                flash('Cannot submit, deadline has passed.', 'error')
                return redirect(url_for('student_view_assignment', assignment_id=assignment.id))
            
            new_submission = AssignmentSubmission(
                assignment_id=assignment.id,
                student_id=current_user.id,
                content=content,
                status='Submitted'
            )
            db.session.add(new_submission)
            db.session.commit()
            flash('Assignment submitted successfully!', 'success')

        return redirect(url_for('student_view_assignment', assignment_id=assignment.id))

    return render_template('student/view_assignment.html',
                           assignment=assignment,
                           submission=submission,
                           can_resubmit=can_resubmit)

@app.route('/teacher/classroom/<int:classroom_id>/assignment/<int:assignment_id>/submissions')
@login_required
def teacher_view_submissions(classroom_id, assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    assignment = Assignment.query.filter_by(id=assignment_id, classroom_id=classroom.id).first_or_404()
    submissions = AssignmentSubmission.query.filter_by(assignment_id=assignment.id).options(joinedload(AssignmentSubmission.student)).order_by(AssignmentSubmission.submitted_at.asc()).all()

    return render_template('teacher/assignment_submissions.html', 
                           classroom=classroom, 
                           assignment=assignment, 
                           submissions=submissions)

@app.route('/teacher/classroom/<int:classroom_id>/assignment/<int:assignment_id>/submission/<int:submission_id>/grade', methods=['GET', 'POST'])
@login_required
def teacher_grade_submission(classroom_id, assignment_id, submission_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    assignment = Assignment.query.filter_by(id=assignment_id, classroom_id=classroom.id).first_or_404()
    submission = AssignmentSubmission.query.options(joinedload(AssignmentSubmission.student)).filter_by(id=submission_id, assignment_id=assignment.id).first_or_404()

    if request.method == 'POST':
        grade = request.form.get('grade')
        feedback = request.form.get('feedback')
        is_resubmission_allowed = request.form.get('is_resubmission_allowed') == 'on'

        if grade:
            try:
                submission.grade = float(grade)
            except ValueError:
                flash('Invalid grade. Please enter a number.', 'error')
                return redirect(url_for('teacher_grade_submission', classroom_id=classroom.id, assignment_id=assignment.id, submission_id=submission.id))
        else:
            submission.grade = None
        
        submission.feedback = feedback
        submission.status = 'Graded'
        submission.is_resubmission_allowed = is_resubmission_allowed
        db.session.commit()
        flash('Submission graded successfully!', 'success')
        return redirect(url_for('teacher_view_submissions', classroom_id=classroom.id, assignment_id=assignment.id))

    return render_template('teacher/grade_submission.html',
                           classroom=classroom,
                           assignment=assignment,
                           submission=submission)

@app.route('/teacher/submission/<int:submission_id>/toggle_resubmission', methods=['POST'])
@login_required
def teacher_toggle_resubmission(submission_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    submission = AssignmentSubmission.query.get_or_404(submission_id)
    
    # Verify that the teacher owns the assignment associated with the submission
    if submission.assignment.teacher_id != current_user.id:
        flash('Access denied: You do not own this assignment.', 'error')
        return redirect(url_for('teacher_dashboard'))

    submission.is_resubmission_allowed = not submission.is_resubmission_allowed
    db.session.commit()

    if submission.is_resubmission_allowed:
        flash('Resubmission enabled for this assignment.', 'success')
    else:
        flash('Resubmission disabled for this assignment.', 'info')
    
    return redirect(url_for('teacher_view_submissions', classroom_id=submission.assignment.classroom_id, assignment_id=submission.assignment.id))
