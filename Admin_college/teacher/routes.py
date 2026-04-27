from flask import render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from . import teacher_bp
import mysql.connector


# ---------------- DB ----------------
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="college_feedback"
    )


# ---------------- TEACHER SIGNUP ----------------
@teacher_bp.route('/signup', methods=['GET', 'POST'])
def teacher_signup():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # get teachers for dropdown
    cursor.execute("SELECT id, name FROM teachers")
    teachers = cursor.fetchall()

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        teacher_id = request.form['teacher_id']

        # check duplicate
        cursor.execute("SELECT * FROM teacher_accounts WHERE email=%s", (email,))
        if cursor.fetchone():
            flash("Account already exists!", "error")
            return redirect('/teacher/signup')

        hashed = generate_password_hash(password)

        # ✔ LINK DIRECTLY TO TEACHER
        cursor.execute("""
            INSERT INTO teacher_accounts (email, password, teacher_id)
            VALUES (%s, %s, %s)
        """, (email, hashed, teacher_id))

        db.commit()
        cursor.close()
        db.close()

        flash("Signup successful! You can login now.", "success")
        return redirect('/teacher/login')

    return render_template('teacher/teacher_signup.html', teachers=teachers)


# ---------------- TEACHER LOGIN ----------------
@teacher_bp.route('/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT ta.id, ta.email, ta.password, ta.teacher_id,
                   t.name, t.department, t.experience, t.status
            FROM teacher_accounts ta
            JOIN teachers t ON ta.teacher_id = t.id
            WHERE ta.email = %s
        """, (email,))

        teacher = cursor.fetchone()

        cursor.close()
        db.close()

        # ❌ no account
        if not teacher:
            flash("Invalid email or password!", "error")
            return redirect('/teacher/login')

        # ❌ wrong password
        if not check_password_hash(teacher['password'], password):
            flash("Invalid email or password!", "error")
            return redirect('/teacher/login')

        # ❌ inactive teacher (IMPORTANT)
        if teacher['status'] != 'active':
            flash("Your account is no longer valid. Contact admin.", "error")
            return redirect('/teacher/login')

        # ✅ SUCCESS LOGIN
        session.clear()
        session['teacher_id'] = teacher['teacher_id']
        session['teacher_name'] = teacher['name']

        return redirect('/teacher/dashboard')

    return render_template('teacher/teacher_login.html')


# ---------------- DASHBOARD ----------------
@teacher_bp.route('/dashboard')
def teacher_dashboard():
    if 'teacher_id' not in session:
        return redirect('/teacher/login')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # teacher info
    cursor.execute("""
        SELECT id, name, department, experience, status, image_url
        FROM teachers
        WHERE id = %s
    """, (session['teacher_id'],))

    teacher = cursor.fetchone()

    # reviews
    cursor.execute("""
    SELECT r.rating, r.review_text, r.created_at,
           s.name AS student_name,
           s.department AS student_department
    FROM reviews r
    LEFT JOIN students s ON r.student_id = s.id
    WHERE r.teacher_id = %s
    ORDER BY r.created_at DESC
""", (session['teacher_id'],))

    reviews = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        'teacher/teacher_dashboard.html',
        teacher=teacher,
        reviews=reviews
    )
@teacher_bp.route('/logout')
def teacher_logout():
    session.clear()
    return redirect('/teacher/login')