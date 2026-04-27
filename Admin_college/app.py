from flask import Flask, render_template, request, redirect, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import timedelta   # ✅ FIX ADDED
import os

# Admin Flask app
app = Flask(__name__, template_folder='templates')
app.secret_key = "admin_secret"

# NOW import blueprint AFTER app is created
from teacher import teacher_bp
app.register_blueprint(teacher_bp, url_prefix='/teacher')

app.config['SESSION_PERMANENT'] = True
app.permanent_session_lifetime = timedelta(days=7)


# ================= DATABASE =================
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="college_feedback"
    )

# ==================role select==============
@app.route('/')
def role_select():
    return render_template('role_select.html')

# ---------------- ADMIN LOGIN ----------------
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if 'admin_id' in session:
        return redirect('/admin/dashboard')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM admins WHERE email=%s", (email,))
        admin = cursor.fetchone()

        cursor.close()
        db.close()

        if admin and check_password_hash(admin['password'], password):

            session.permanent = True   # ✅ FIX IMPORTANT (session persists on refresh)

            session['admin_id'] = admin['id']
            session['admin_name'] = admin['name']

            return redirect('/admin/dashboard')
        else:
            flash("Invalid login!", "error")
            return redirect('/admin/login')

    return render_template('admin_login.html')


# ---------------- ADMIN SIGNUP ----------------
@app.route('/admin/signup', methods=['GET','POST'])
def admin_signup():
    if 'admin_id' in session:
        return redirect('/admin/dashboard')

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM admins WHERE email=%s", (email,))
        if cursor.fetchone():
            flash("Admin already exists!", "error")
            cursor.close()
            db.close()
            return redirect('/admin/signup')

        hashed = generate_password_hash(password)

        cursor.execute(
            "INSERT INTO admins (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed)
        )

        db.commit()
        cursor.close()
        db.close()

        flash("Signup successful! You can now login.", "success")
        return redirect('/admin/login')

    return render_template('admin_signup.html')


# ---------------- ADMIN DASHBOARD ----------------
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM teachers")
    total_teachers = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM students")
    total_students = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM reviews")
    total_reviews = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM teachers WHERE status='active'")
    active_teachers = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM teachers WHERE status='inactive'")
    inactive_teachers = cursor.fetchone()['total']

    cursor.execute("SELECT * FROM teachers")
    teachers = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        'admin_dashboard.html',
        total_teachers=total_teachers,
        total_students=total_students,
        total_reviews=total_reviews,
        active_teachers=active_teachers,
        inactive_teachers=inactive_teachers,
        teachers=teachers,
        admin_name=session.get('admin_name')
    )


# ---------------- ADD TEACHER ----------------
@app.route('/admin/add_teacher', methods=['GET','POST'])
def add_teacher():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    if request.method == 'POST':
        name = request.form['name']
        department = request.form['department']
        experience = request.form['experience']
        admin_review = request.form['admin_review']

        image_file = request.files.get('image_file')

        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            images_folder = os.path.join(app.root_path, 'static', 'images')
            os.makedirs(images_folder, exist_ok=True)
            filepath = os.path.join(images_folder, filename)
            image_file.save(filepath)
        else:
            filename = 'profile.png'

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            "INSERT INTO teachers (name, department, experience, image_url, admin_review, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (name, department, experience, filename, admin_review, 'active')
        )

        db.commit()
        cursor.close()
        db.close()

        flash("Teacher added successfully!", "success")
        return redirect('/admin/dashboard')

    return render_template('add_teacher.html')


# ---------------- ADMIN TEACHERS ----------------
@app.route('/admin/teachers')
def admin_teachers():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM teachers")
    teachers = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        'admin_teachers.html',
        teachers=teachers,
        admin_name=session.get('admin_name')
    )


# ---------------- ADMIN REVIEWS ----------------
@app.route('/admin/reviews', methods=['GET'])
def admin_review():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    search_query = request.args.get('query', '').strip()
    sort_by = request.args.get('sort', 'date_desc')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT r.id, r.rating, r.review_text,
               r.created_at,
               COALESCE(s.name, 'Unknown Student') AS student_name,
               COALESCE(r.department, 'N/A') AS student_department,
               COALESCE(t.name, 'Unknown Teacher') AS teacher_name
        FROM reviews r
        LEFT JOIN students s ON r.student_id = s.id
        LEFT JOIN teachers t ON r.teacher_id = t.id
    """)

    reviews = cursor.fetchall()

    cursor.close()
    db.close()

    if search_query:
        search_lower = search_query.lower()
        reviews = [
            r for r in reviews
            if search_lower in str(r['student_name']).lower()
            or search_lower in str(r['teacher_name']).lower()
            or search_lower in str(r['review_text']).lower()
        ]

    for r in reviews:
        if r['created_at'] is None:
            r['created_at'] = '1970-01-01 00:00:00'

    if sort_by == 'rating_asc':
        reviews.sort(key=lambda x: x['rating'])
    elif sort_by == 'rating_desc':
        reviews.sort(key=lambda x: x['rating'], reverse=True)
    elif sort_by == 'student_name':
        reviews.sort(key=lambda x: x['student_name'].lower())
    elif sort_by == 'teacher_name':
        reviews.sort(key=lambda x: x['teacher_name'].lower())
    elif sort_by == 'date_asc':
        reviews.sort(key=lambda x: x['created_at'])
    else:
        reviews.sort(key=lambda x: x['created_at'], reverse=True)

    return render_template(
        "admin_review.html",
        reviews=reviews,
        admin_name=session.get("admin_name"),
        query=search_query,
        sort_by=sort_by
    )


# ---------------- ADMIN LOGOUT ----------------
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    flash("Logged out successfully!", "success")
    return redirect('/admin/login')


# ---------------- TEACHER STATUS PAGE ----------------
@app.route('/admin/teacher_status')
def teacher_status():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM teachers")
    teachers = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("teacher_status.html", teachers=teachers)


# ---------------- TEACHER PROFILE ----------------
@app.route('/admin/teacher/<int:id>')
def teacher_profile(id):
    if 'admin_id' not in session:
        return redirect('/admin/login')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM teachers WHERE id=%s", (id,))
    teacher = cursor.fetchone()

    cursor.close()
    db.close()

    if not teacher:
        flash("Teacher not found!", "error")
        return redirect('/admin/teacher_status')

    return render_template("teacher_profile.html", teacher=teacher)


# ---------------- STATUS UPDATE ----------------
@app.route('/admin/teacher/<int:id>/status/<string:state>')
def update_teacher_status(id, state):
    if 'admin_id' not in session:
        return redirect('/admin/login')

    if state not in ['active', 'inactive']:
        return redirect('/admin/teacher_status')

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "UPDATE teachers SET status=%s WHERE id=%s",
        (state, id)
    )

    db.commit()
    cursor.close()
    db.close()

    return redirect(f'/admin/teacher/{id}')


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True, port=5001)