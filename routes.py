import os
import json
import csv
import io
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, jsonify, send_file, make_response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from app import app, db
from models import User, Classroom, Enrollment, Material, SelfEvaluation
from ai_service import AIService
from utils import allowed_file, extract_text_from_file
from firebase_service import firebase_service

ai_service = AIService()

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
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('auth/login.html',
                          firebase_api_key=os.environ.get("FIREBASE_API_KEY"),
                          firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID"),
                          firebase_app_id=os.environ.get("FIREBASE_APP_ID"),
                          firebase_messaging_sender_id=os.environ.get("FIREBASE_MESSAGING_SENDER_ID"))

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

@app.route('/auth/firebase', methods=['POST'])
def auth_firebase():
    """Handle Firebase authentication"""
    try:
        data = request.get_json()
        print(f"Firebase auth request received: {data}")
        
        # For testing purposes, let's also accept user info directly
        # This is a fallback when Firebase Admin SDK isn't available
        email = data.get('email')
        name = data.get('name', '')
        firebase_uid = data.get('uid')
        id_token = data.get('idToken')
        
        print(f"Extracted data - Email: {email}, Name: {name}, UID: {firebase_uid}")
        
        if not email:
            print("Error: No email found in request")
            return jsonify({'success': False, 'error': 'No email found in request'}), 400
        
        # Determine role based on email domain
        role = firebase_service.get_user_role_from_email(email)
        
        # Split name into first and last name
        name_parts = name.split(' ', 1) if name else ['', '']
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Check if user exists, if not create them
        user = User.query.filter_by(email=email).first()
        print(f"User lookup result: {user}")
        
        if not user:
            print(f"Creating new user with email: {email}, role: {role}")
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                firebase_uid=firebase_uid,
                password_hash='firebase_user'  # Placeholder for Firebase users
            )
            db.session.add(user)
            db.session.commit()
            print(f"New user created with ID: {user.id}")
        else:
            print(f"Updating existing user: {user.id}")
            # Update user info if it has changed
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
            user.role = role
            if firebase_uid:
                user.firebase_uid = firebase_uid
            db.session.commit()
            print("User updated successfully")
        
        # Log the user in
        print(f"Logging in user: {user.email}")
        login_user(user)
        print("User logged in successfully")
        
        # Return success response with redirect URL
        if role == 'teacher':
            redirect_url = url_for('teacher_dashboard')
        else:
            redirect_url = url_for('student_dashboard')
            
        return jsonify({
            'success': True, 
            'redirect_url': redirect_url,
            'role': role,
            'name': user.full_name
        })
        
    except Exception as e:
        print(f"Firebase auth error: {str(e)}")
        return jsonify({'success': False, 'error': 'Authentication failed'}), 500

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
    
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id).all()
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
    
    return render_template('teacher/classroom.html', 
                         classroom=classroom, 
                         materials=materials,
                         students=students)

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

# Student routes
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    classrooms = [enrollment.classroom for enrollment in enrollments]
    
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
    ).filter(SelfEvaluation.completed_at.isnot(None)).order_by(SelfEvaluation.completed_at.desc()).limit(5).all()
    
    return render_template('student/classroom.html', 
                         classroom=classroom, 
                         materials=materials,
                         recent_evaluations=recent_evaluations)

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
    materials = Material.query.filter_by(classroom_id=classroom_id).all()
    
    if not materials:
        flash('No materials available for study guide generation', 'warning')
        return redirect(url_for('student_classroom', classroom_id=classroom_id))
    
    try:
        # Combine all material content
        combined_content = "\n\n".join([f"**{material.title}**\n{material.content}" for material in materials if material.content])
        
        study_guide = ai_service.generate_study_guide(combined_content, classroom.name)
        
        return render_template('student/study_guide.html', 
                             classroom=classroom, 
                             study_guide=study_guide)
    
    except Exception as e:
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

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error_message='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error_message='An internal error occurred'), 500
