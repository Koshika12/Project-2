from flask import Flask, render_template, request, redirect, session, flash, url_for
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = "college_secret"

# Database connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="college_feedback"
)

# ===================== SIGN UP =====================
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        batch = request.form['batch']
        department = request.form['department']

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM students WHERE email=%s", (email,))
        existing = cursor.fetchone()
        if existing:
            flash("Email already registered!", "error")
            cursor.close()
            return redirect('/signup')

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
        cursor.execute(
            "INSERT INTO students (name,email,password,batch,department) VALUES (%s,%s,%s,%s,%s)",
            (name, email, hashed_password, batch, department)
        )
        db.commit()
        cursor.close()
        flash("Sign up successful! You can now log in.", "success")
        return redirect('/login')

    return render_template('signup.html')


# ===================== LOGIN =====================
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'student_id' in session:
        return redirect('/dashboard')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM students WHERE email=%s", (email,))
        student = cursor.fetchone()
        cursor.close()

        if student and check_password_hash(student['password'], password):
            session['student_id'] = student['id']
            session['student_name'] = student['name']
            return redirect('/dashboard')
        else:
            flash("Invalid email or password!", "error")
            return redirect('/login')

    return render_template('login.html')


# ===================== DASHBOARD =====================
@app.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect('/login')

    cursor = db.cursor(dictionary=True)

    # Total teachers
    cursor.execute("SELECT COUNT(*) AS total FROM teachers")
    total_teachers = cursor.fetchone()['total']

    # Total reviews
    cursor.execute("SELECT COUNT(*) AS total FROM reviews")
    total_reviews = cursor.fetchone()['total']

    # Average rating
    cursor.execute("SELECT AVG(rating) AS avg_rating FROM reviews")
    avg_rating = cursor.fetchone()['avg_rating'] or 0
    avg_rating = round(avg_rating, 1)

    # Teachers with reviews
    cursor.execute("""
        SELECT t.id, t.name, t.department, t.image_url, t.admin_review,
               IFNULL(AVG(r.rating), 0) AS avg_rating,
               COUNT(r.id) AS reviews_count
        FROM teachers t
        LEFT JOIN reviews r ON t.id = r.teacher_id
        GROUP BY t.id
        ORDER BY avg_rating DESC, reviews_count DESC
    """)
    top_teachers = cursor.fetchall()
    cursor.close()

    # Fix defaults
    for t in top_teachers:
        t['avg_rating'] = round(t['avg_rating'], 1)
        if not t['image_url'] or not os.path.isfile(os.path.join(app.root_path, 'static', 'images', t['image_url'])):
            t['image_url'] = 'profile.png'
        if not t['admin_review'] or t['admin_review'].strip() == "":
            t['admin_review'] = "No description available."

    return render_template(
        'dashboard.html',
        total_teachers=total_teachers,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        top_teachers=top_teachers
    )


# ===================== LOGOUT =====================
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect('/login')


# ===================== TEACHERS LIST =====================
@app.route('/teachers')
def teachers():
    if 'student_id' not in session:
        return redirect('/login')

    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT t.id, t.name, t.department, t.image_url, t.admin_review,
               IFNULL(COUNT(r.id),0) AS reviews_count,
               IFNULL(AVG(r.rating),0) AS avg_rating
        FROM teachers t
        LEFT JOIN reviews r ON t.id = r.teacher_id
        GROUP BY t.id
        ORDER BY avg_rating DESC, reviews_count DESC
    """)
    teacher_list = cursor.fetchall()
    cursor.close()

    # Fix defaults
    for t in teacher_list:
        t['avg_rating'] = round(t['avg_rating'], 1)
        if not t['image_url'] or not os.path.isfile(os.path.join(app.root_path, 'static', 'images', t['image_url'])):
            t['image_url'] = 'profile.png'
        if not t['admin_review'] or t['admin_review'].strip() == "":
            t['admin_review'] = "No description available."

    return render_template(
        'teachers.html',
        student_name=session['student_name'],
        teachers=teacher_list
    )


# ===================== TEACHER INFO =====================
@app.route('/teacher/<int:teacher_id>')
def teacher_info(teacher_id):
    if 'student_id' not in session:
        return redirect('/login')

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM teachers WHERE id=%s", (teacher_id,))
    teacher = cursor.fetchone()
    cursor.close()

    if not teacher:
        flash("Teacher not found!", "error")
        return redirect('/teachers')

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT AVG(rating) AS avg_rating FROM reviews WHERE teacher_id=%s", (teacher_id,))
    avg = cursor.fetchone()
    cursor.close()
    avg_rating = round(avg['avg_rating'], 2) if avg['avg_rating'] else "Not rated yet"

    if not teacher['image_url']:
        teacher['image_url'] = 'profile.png'

    return render_template(
        'teacher_info.html',
        student_name=session['student_name'],
        teacher=teacher,
        avg_rating=avg_rating
    )


# ===================== SUBMIT REVIEW =====================
@app.route('/review', methods=['GET', 'POST'])
def review():
    if 'student_id' not in session:
        return redirect('/login')

    teacher_id = request.args.get('teacher_id')

    # Case: No teacher selected yet
    if not teacher_id:
        return render_template(
            'review.html',
            student_name=session['student_name'],
            teacher=None,
            show_form=False,
            message="Please select a teacher to give your review."
        )

    # Fetch teacher info
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM teachers WHERE id=%s", (teacher_id,))
    teacher = cursor.fetchone()
    cursor.close()

    if not teacher:
        flash("Teacher not found!", "error")
        return redirect('/teachers')

    # Handle form submission
    if request.method == 'POST':
        rating = int(request.form['rating'])
        review_text = request.form['review']

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO reviews (student_id, teacher_id, rating, review_text) VALUES (%s,%s,%s,%s)",
            (session['student_id'], teacher_id, rating, review_text)
        )
        db.commit()
        cursor.close()

        # Show success message on same page
        return render_template(
            'review.html',
            student_name=session['student_name'],
            teacher=None,
            show_form=False,
            message=None,
            success=True
        )

    return render_template(
        'review.html',
        student_name=session['student_name'],
        teacher=teacher,
        show_form=True,
        success=False,
        message=None
    )


if __name__ == "__main__":
    os.makedirs('static/images', exist_ok=True)
    app.run(debug=True)