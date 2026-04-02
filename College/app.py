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
@app.route('/dashboard', methods=['GET'])
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

    # Fetch all teachers WITHOUT ORDER BY
    cursor.execute("""
        SELECT t.id, t.name, t.department, t.image_url, t.admin_review,
               IFNULL(AVG(r.rating), 0) AS avg_rating,
               COUNT(r.id) AS reviews_count
        FROM teachers t
        LEFT JOIN reviews r ON t.id = r.teacher_id
        GROUP BY t.id
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

    # ===== SEARCH FUNCTIONALITY (Linear Search) =====
    search_query = request.args.get('search', '').lower()
    if search_query:
        filtered_teachers = []
        for t in top_teachers:
            if search_query in t['name'].lower() or search_query in t['department'].lower():
                filtered_teachers.append(t)
        top_teachers = filtered_teachers

    # ===== SORTING FUNCTIONALITY (Bubble Sort
    # ) =====
    sort_by = request.args.get('sort', 'rating_desc')  # default
    n = len(top_teachers)
    for i in range(n):
        for j in range(0, n-i-1):
            swap = False
            if sort_by == 'rating_desc' and top_teachers[j]['avg_rating'] < top_teachers[j+1]['avg_rating']:
                swap = True
            elif sort_by == 'rating_asc' and top_teachers[j]['avg_rating'] > top_teachers[j+1]['avg_rating']:
                swap = True
            elif sort_by == 'reviews_desc' and top_teachers[j]['reviews_count'] < top_teachers[j+1]['reviews_count']:
                swap = True
            elif sort_by == 'reviews_asc' and top_teachers[j]['reviews_count'] > top_teachers[j+1]['reviews_count']:
                swap = True
            if swap:
                top_teachers[j], top_teachers[j+1] = top_teachers[j+1], top_teachers[j]

    return render_template(
        'dashboard.html',
        total_teachers=total_teachers,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        top_teachers=top_teachers,
        search_query=search_query,
        sort_by=sort_by
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

    # Get search and sort parameters
    search_term = request.args.get('search', '').strip().lower()
    sort_by = request.args.get('sort', 'highest')

    cursor = db.cursor(dictionary=True)

    # Fetch ALL teachers (no search/sort in SQL)
    cursor.execute("""
        SELECT t.id, t.name, t.department, t.image_url, t.admin_review,
               IFNULL(COUNT(r.id),0) AS reviews_count,
               IFNULL(AVG(r.rating),0) AS avg_rating
        FROM teachers t
        LEFT JOIN reviews r ON t.id = r.teacher_id
        GROUP BY t.id
    """)
    teacher_list = cursor.fetchall()
    cursor.close()

    # ================= SEARCHING ALGORITHM (LINEAR SEARCH) =================
    if search_term:
        filtered_list = []
        for t in teacher_list:   # Linear Search
            if (search_term in t['name'].lower() or 
                search_term in t['department'].lower()):
                filtered_list.append(t)
        teacher_list = filtered_list

    # ================= SORTING ALGORITHM =================
    # Using Python sort (Timsort)
    if sort_by == "alphabet":
        teacher_list.sort(key=lambda x: x['name'])

    elif sort_by == "highest":
        teacher_list.sort(key=lambda x: x['avg_rating'], reverse=True)

    elif sort_by == "lowest":
        teacher_list.sort(key=lambda x: x['avg_rating'])

    # ================= DATA CLEANING =================
    for t in teacher_list:
        t['avg_rating'] = round(t['avg_rating'], 1)

        if not t['image_url'] or not os.path.isfile(
            os.path.join(app.root_path, 'static', 'images', t['image_url'])
        ):
            t['image_url'] = 'profile.png'

        if not t['admin_review'] or t['admin_review'].strip() == "":
            t['admin_review'] = "No description available."

    return render_template(
        'teachers.html',
        student_name=session['student_name'],
        teachers=teacher_list,
        current_sort=sort_by,
        current_search=search_term
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

    # Fetch student department
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT department FROM students WHERE id=%s", (session['student_id'],))
    student = cursor.fetchone()
    cursor.close()
    student_department = student['department'] if student else "N/A"

    # Case: No teacher selected
    if not teacher_id:
        return render_template(
            'review.html',
            student_name=session['student_name'],
            student_department=student_department,
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
            "INSERT INTO reviews (student_id, department, teacher_id, rating, review_text) VALUES (%s,%s,%s,%s,%s)",
            (session['student_id'], student_department, teacher_id, rating, review_text)
        )
        db.commit()
        cursor.close()

        return render_template(
            'review.html',
            student_name=session['student_name'],
            student_department=student_department,
            teacher=None,
            show_form=False,
            message=None,
            success=True
        )

    # Default: show review form
    return render_template(
        'review.html',
        student_name=session['student_name'],
        student_department=student_department,
        teacher=teacher,
        show_form=True,
        success=False,
        message=None
    )
#====================delete review============
@app.route('/delete_review/<int:review_id>')
def delete_review(review_id):
    if 'student_id' not in session:
        return redirect('/login')

    cursor = db.cursor()
    cursor.execute("DELETE FROM reviews WHERE id=%s AND student_id=%s", 
                   (review_id, session['student_id']))
    db.commit()
    cursor.close()
    flash("Review deleted successfully!", "success")
    return redirect('/teachers')

#================insert review in history table===============
@app.route('/submit_review', methods=['POST'])
def submit_review():
    if 'student_id' in session:
        student_id = session['student_id']
        teacher_id = request.form['teacher_id']
        rating = request.form['rating']
        review_text = request.form['review_text']

        cursor = db.cursor()
        # Insert review into history table
        cursor.execute("""
            INSERT INTO history (student_id, teacher_id, review_rating, review_text)
            VALUES (%s, %s, %s, %s)
        """, (student_id, teacher_id, rating, review_text))
        db.commit()
        cursor.close()
        
        flash('Review submitted successfully!', 'success')
        return redirect('/student_dashboard')
    else:
        flash('Please login first!', 'error')
        return redirect('/student_login')
    #=================History=====================

@app.route('/history')
def history():
    if 'student_id' not in session:
        return redirect('/login')

    student_id = session['student_id']

    cursor = db.cursor(dictionary=True)

    # Fetch WITHOUT ORDER BY
    cursor.execute("""
        SELECT r.review_text, r.rating, r.created_at, t.name AS teacher_name
        FROM reviews r
        JOIN teachers t ON r.teacher_id = t.id
        WHERE r.student_id = %s
    """, (student_id,))

    reviews = cursor.fetchall()
    cursor.close()

    # ================= SORTING ALGORITHM =================
    # Sort by latest date (descending)
    reviews.sort(key=lambda x: x['created_at'], reverse=True)

    return render_template('history.html', reviews=reviews)


if __name__ == "__main__":
    os.makedirs('static/images', exist_ok=True)
    app.run(debug=True)