# AI Classroom Companion

## Project Description

This is a Flask-based web application designed to assist both teachers and students in a classroom environment. It leverages AI capabilities (**Gemini** is used in this example) to generate study guides and quizzes based on uploaded material, facilitates classroom management, and provides tools for tracking student progress.

## Features

*   **User Authentication:** Secure login and registration for teachers and students.
*   **Role-Based Access Control (RBAC):** Differentiates user permissions based on 'teacher' and 'student' roles.
*   **Classroom Management:** Teachers can create classrooms, add/remove students, and manage materials.
*   **Material Management:** Teachers can upload study materials (PDF, text files) to classrooms.
*   **AI Study Guide Generation:** Students can generate study guides based on classroom materials using AI.

-   Here's an example of an AI-generated study guide:
-
-   ![AI Generated Study Guide](https://firebasestorage.googleapis.com/v0/b/markdown-editor-fa4c0.appspot.com/o/images%2Fai-study-guide.png?alt=media&token=65e3b3b6-8041-4792-a88d-94f8403a361e)
-
*   **AI Quiz Generation:** Students can generate quizzes (MCQ, True/False, Essay) based on classroom materials using AI.
*   **Teacher Quiz Management:** Teachers can create, edit, publish, and delete their own quizzes.
*   **Quiz Taking and Scoring:** Students can take AI-generated and teacher-created quizzes, with automatic scoring for objective types and AI scoring for essays.
*   **Progress Tracking:** Teachers can view student performance and quiz results.
*   **Data Export:** Teachers can export student results.
*   **Secure Password Handling:** Uses `werkzeug.security` for password hashing.
*   **Database Migrations:** Uses Flask-Migrate/Alembic for managing database schema changes.

## Prerequisites

Before you begin, ensure you have met the following requirements:

*   Python 3.6+
*   pip (Python package installer)
*   Git
*   A PostgreSQL database (Supabase is used in this example, but any PostgreSQL database should work)
*   Docker and Docker Compose (if you plan to run the application using Docker)

## Setup Instructions

Follow these steps to set up the project locally for development:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/andrewtliem/atlverse-classroom.git
    cd atlverse-classroom
    ```

2.  **Create and activate a Python virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    Create a `.env` file in the root directory of the project. This file will store your application's configuration secrets and settings. At minimum, you need:

    *   `DATABASE_URL`: Your database connection string (e.g., from Supabase).
    *   `SESSION_SECRET`: A strong, random secret key for Flask sessions.

    Your `.env` file should look like this:
    ```dotenv
    DATABASE_URL=postgresql://YOUR_USERNAME:YOUR_PASSWORD@YOUR_HOST:YOUR_PORT/YOUR_DBNAME
    SESSION_SECRET=a_very_long_and_random_secret_key_here
    # Add other environment variables your AI service might require (e.g., API keys)
    # Example: GEMINI_API_KEY=your_gemini_key
    ```
    **Replace the placeholder values with your actual credentials and keys.**

5.  **Run Database Migrations:**
    Apply the database migrations to create the necessary tables in your configured database. Ensure your database is empty or you understand the current state of your database schema before running migrations, especially the initial ones.

    ```bash
    export FLASK_APP=app.py
    flask db upgrade
    ```

## Running the Application

### Local Development Server

To run the application using Flask's built-in development server:

```bash
export FLASK_APP=app.py
flask run --host=0.0.0.0 --port=5001 --debug
```
The application will be accessible at `http://127.0.0.1:5001/`.

### Using Docker Compose

If you have Docker and Docker Compose installed, you can run the application in a container:

1.  **Ensure your `.env` file is present** in the project root with `DATABASE_URL`, `SESSION_SECRET`, and any AI service API keys set correctly for the environment Docker will run in.

2.  **Build the Docker image:**
    ```bash
    docker-compose build
    ```

3.  **Run database migrations inside the container:**
    ```bash
    docker-compose run web flask db upgrade
    ```

4.  **Start the application container:**
    ```bash
    docker-compose up -d
    ```

The application will be running inside the container, typically accessible on the host machine at the port mapped in `docker-compose.yml` (defaulting to `http://127.0.0.1:8000`).

## Project Structure (Simplified)

```
atlverse-classroom/
├── migrations/         # Alembic migration scripts
│   ├── versions/
│   └── ...
├── app/
│   ├── __init__.py     # Flask app creation
│   ├── models.py       # Database models
│   ├── routes.py       # Flask routes (views)
│   ├── ai_service.py   # AI interaction logic
│   └── utils.py        # Helper functions
├── templates/          # Jinja2 HTML templates
├── static/             # Static assets (CSS, JS, images)
├── .env                # Environment variables (NOT tracked by Git)
├── .gitignore          # Specifies intentionally untracked files
├── requirements.txt    # Project dependencies
├── Dockerfile          # Instructions for building the Docker image
├── docker-compose.yml  # Defines how to run the application with Docker
├── README.md           # This file
└── ... other files
```

## Security Considerations

While basic security measures are in place, consider enhancing the following:

*   Comprehensive input validation and sanitization using libraries like WTForms.
*   CSRF protection for all forms (e.g., using Flask-WTF).
*   Rate limiting to prevent brute-force attacks on login/registration.
*   More granular Role-Based Access Control if needed.


## Screenshots

Here's an example screenshot of the application:

![AI Generated Study Guide](screenshots/Study_Guide_AI_Student.png)

![Student Dashboard](screenshots/Classroom_Student.png)

![Teacher Dashboard](screenshots/Dashboard_Teacher.png)
