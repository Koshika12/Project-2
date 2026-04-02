from flask import Flask, render_template, request, redirect, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

# Admin Flask app
app = Flask(__name__, template_folder='templates')  # Use separate templates folder
app.secret_key = "admin_secret"

# Database connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="college_feedback"
)

# ---------------- ADMIN LOGIN ----------------
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if 'admin_id' in session:
        return redirect('/admin/dashboard')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE email=%s", (email,))
        admin = cursor.fetchone()
        cursor.close()

        if admin and check_password_hash(admin['password'], password):
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

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE email=%s", (email,))
        if cursor.fetchone():
            flash("Admin already exists!", "error")
            cursor.close()
            return redirect('/admin/signup')

        hashed = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO admins (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed)
        )
        db.commit()
        cursor.close()

        flash("Signup successful! You can now login.", "success")
        return redirect('/admin/login')

    return render_template('admin_signup.html')


# ---------------- ADMIN DASHBOARD ----------------
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    cursor = db.cursor(dictionary=True)

    # Stats
    cursor.execute("SELECT COUNT(*) AS total FROM teachers")
    total_teachers = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM students")
    total_students = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM reviews")
    total_reviews = cursor.fetchone()['total']

    # Teachers list
    cursor.execute("SELECT * FROM teachers")
    teachers = cursor.fetchall()
    cursor.close()

    return render_template('admin_dashboard.html',
                           total_teachers=total_teachers,
                           total_students=total_students,
                           total_reviews=total_reviews,
                           teachers=teachers,
                           admin_name=session.get('admin_name'))


# ---------------- ADD TEACHER ----------------
from werkzeug.utils import secure_filename
import os

@app.route('/admin/add_teacher', methods=['GET','POST'])
def add_teacher():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    if request.method == 'POST':
        name = request.form['name']
        department = request.form['department']
        experience = request.form['experience']
        admin_review = request.form['admin_review']

        # Handle uploaded image
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            images_folder = os.path.join(app.root_path, 'static', 'images')
            os.makedirs(images_folder, exist_ok=True)
            filepath = os.path.join(images_folder, filename)
            image_file.save(filepath)
        else:
            filename = 'profile.png'  # default image if none uploaded

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO teachers (name, department, experience, image_url, admin_review) VALUES (%s, %s, %s, %s, %s)",
            (name, department, experience, filename, admin_review)
        )
        db.commit()
        cursor.close()

        flash("Teacher added successfully!", "success")
        return redirect('/admin/dashboard')

    return render_template('add_teacher.html')
@app.route('/admin/teachers')
def admin_teachers():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM teachers")
    teachers = cursor.fetchall()
    cursor.close()

    return render_template('admin_teachers.html',
                           teachers=teachers,
                           admin_name=session.get('admin_name'))


# ---------------- REVIEW ----------------
@app.route('/admin/reviews', methods=['GET'])
def admin_review():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    # 1️⃣ Get search and sort query parameters
    search_query = request.args.get('query', '').strip()
    sort_by = request.args.get('sort', 'date_desc')  # default sort

    # 2️⃣ Fetch all reviews from database
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.id, r.rating, r.review_text, r.created_at,
               s.name AS student_name,
               s.department AS student_department,
               t.name AS teacher_name
        FROM reviews r
        LEFT JOIN students s ON r.student_id = s.id
        LEFT JOIN teachers t ON r.teacher_id = t.id
    """)
    reviews = cursor.fetchall()
    cursor.close()

    # 3️⃣ SEARCH (Linear Search)
    if search_query:
        search_query_lower = search_query.lower()
        filtered_reviews = []
        for review in reviews:
            if (search_query_lower in str(review['student_name']).lower() or
                search_query_lower in str(review['teacher_name']).lower() or
                search_query_lower in str(review['review_text']).lower()):
                filtered_reviews.append(review)
        reviews = filtered_reviews

    # 4️⃣ SORT (Quick Sort)
    def quick_sort(data, field, reverse=False):
        if len(data) <= 1:
            return data
        pivot = data[0]
        left = [x for x in data[1:] if (x[field] < pivot[field] and not reverse) or (x[field] > pivot[field] and reverse)]
        right = [x for x in data[1:] if (x[field] >= pivot[field] and not reverse) or (x[field] <= pivot[field] and reverse)]
        return quick_sort(left, field, reverse) + [pivot] + quick_sort(right, field, reverse)

    # Determine sort field and order
    if sort_by == 'rating_asc':
        reviews = quick_sort(reviews, 'rating', reverse=False)
    elif sort_by == 'rating_desc':
        reviews = quick_sort(reviews, 'rating', reverse=True)
    elif sort_by == 'student_name':
        reviews = quick_sort(reviews, 'student_name')
    elif sort_by == 'teacher_name':
        reviews = quick_sort(reviews, 'teacher_name')
    elif sort_by == 'date_asc':
        reviews = quick_sort(reviews, 'created_at')
    else:  # date_desc
        reviews = quick_sort(reviews, 'created_at', reverse=True)

    # 5️⃣ Render template
    return render_template("admin_review.html",
                           reviews=reviews,
                           admin_name=session.get("admin_name"),
                           query=search_query,
                           sort_by=sort_by)

# ---------------- ADMIN LOGOUT ----------------
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    flash("Logged out successfully!", "success")
    return redirect('/admin/login')


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True, port=5001)