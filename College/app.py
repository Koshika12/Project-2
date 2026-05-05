from flask import Flask, render_template, request, redirect, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "college_secret"
app.permanent_session_lifetime = timedelta(days=7)

# ================= DATABASE (FIXED PROPERLY) =================
def get_db():
    return mysql.connector.connect(
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

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM students WHERE email=%s", (email,))
        existing = cursor.fetchone()

        if existing:
            flash("Email already registered!", "error")
            cursor.close()
            db.close()
            return redirect('/signup')

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)

        cursor.execute(
            "INSERT INTO students (name,email,password,batch,department) VALUES (%s,%s,%s,%s,%s)",
            (name, email, hashed_password, batch, department)
        )

        db.commit()
        cursor.close()
        db.close()

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

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM students WHERE email=%s", (email,))
        student = cursor.fetchone()

        cursor.close()
        db.close()

        if student and check_password_hash(student['password'], password):
            session.permanent = True
            session['student_id'] = student['id']
            session['student_name'] = student['name']
            session['student_department'] = student['department']
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

    search_term = request.args.get('search', '').strip().lower()
    sort_by = request.args.get('sort', 'highest')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT t.id, t.name, t.department, t.image_url, t.admin_review, t.experience,
               r.rating
        FROM teachers t
        LEFT JOIN reviews r ON t.id = r.teacher_id
        WHERE t.status = 'active'
        ORDER BY t.id DESC
    """)

    data = cursor.fetchall()
    cursor.close()
    db.close()

    # ---------------- GROUPING ----------------
    teachers_dict = {}

    for row in data:
        tid = row['id']

        if tid not in teachers_dict:
            teachers_dict[tid] = {
                'id': tid,
                'name': row['name'],
                'department': row['department'],
                'image_url': row['image_url'],
                'admin_review': row['admin_review'],
                'experience': row['experience'] or 0,
                'reviews': [],
                'avg_rating': 0,
                'reviews_count': 0
            }

        if row['rating'] is not None:
            teachers_dict[tid]['reviews'].append(row['rating'])

    # ---------------- CALCULATE RATINGS ----------------
    teacher_list = list(teachers_dict.values())

    for t in teacher_list:
        reviews = t['reviews']
        n = len(reviews)

        t['reviews_count'] = n

        if n > 0:
            t['avg_rating'] = round(sum(reviews) / n, 1)
        else:
            t['avg_rating'] = 0

    # ---------------- SEARCH FILTER ----------------
    if search_term:
        teacher_list = [
            t for t in teacher_list
            if search_term in t['name'].lower()
            or search_term in t['department'].lower()
        ]

    # ---------------- SORTING (BUBBLE SORT) ----------------
    n = len(teacher_list)

    for i in range(n):
        for j in range(n - i - 1):

            a = teacher_list[j]
            b = teacher_list[j + 1]

            if (
                (sort_by == 'alphabet' and a['name'] > b['name']) or
                (sort_by == 'highest' and a['avg_rating'] < b['avg_rating']) or
                (sort_by == 'lowest' and a['avg_rating'] > b['avg_rating']) or
                (sort_by == 'experience' and a['experience'] < b['experience'])
            ):
                teacher_list[j], teacher_list[j + 1] = b, a

    # ---------------- TOP TEACHERS ----------------
    top_teachers = [t for t in teacher_list if t['avg_rating'] >= 3]

    # ---------------- NORMALIZATION ----------------
    for t in teacher_list:

        if not t['image_url'] or not os.path.isfile(
            os.path.join(app.root_path, 'static', 'images', t['image_url'])
        ):
            t['image_url'] = 'profile.png'

        if not t['admin_review'] or t['admin_review'].strip() == "":
            t['admin_review'] = "No description available."

    # ---------------- METRICS ----------------
    total_teachers = len(teacher_list)

    total_reviews = sum(t['reviews_count'] for t in teacher_list)

    avg_rating = (
        round(
            sum(t['avg_rating'] for t in teacher_list if t['reviews_count'] > 0)
            / total_teachers, 1
        )
        if total_teachers > 0 else 0
    )

    return render_template(
        'dashboard.html',
        total_teachers=total_teachers,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        top_teachers=top_teachers,
        all_teachers=teacher_list,
        search_term=search_term,
        sort_by=sort_by
    )

# ===================== TEACHERS LIST =====================
@app.route('/teachers')
def teachers():

    # ---------------- INPUT CONDITION ----------------
    if 'student_id' not in session:
        return redirect('/login')

    search_term = request.args.get('search', '').strip().lower()
    sort_by = request.args.get('sort', 'highest')

    # ---------------- DATA COLLECTION ----------------
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT t.id, t.name, t.department, t.image_url, t.admin_review,
               t.experience, t.status,
               r.rating
        FROM teachers t
        LEFT JOIN reviews r ON t.id = r.teacher_id
        WHERE t.status = 'active'
        ORDER BY t.id DESC
    """)

    D = cursor.fetchall()
    cursor.close()
    db.close()

    # ---------------- GROUPING ----------------
    M = {}

    for row in D:

        tid = row['id']

        # FIX: ∉ → not in
        if tid not in M:
            M[tid] = {
                'id': tid,
                'name': row['name'],
                'department': row['department'],
                'image_url': row['image_url'],
                'admin_review': row['admin_review'],
                'experience': row['experience'] or 0,
                'status': row['status'],
                'reviews': [],
                'avg_rating': 0,
                'reviews_count': 0
            }

        if row['rating'] is not None:
            M[tid]['reviews'].append(row['rating'])

    # ---------------- AVERAGE RATING ----------------
    L = list(M.values())

    for t in L:

        R = t['reviews']
        n = len(R)

        t['reviews_count'] = n

        if n > 0:
            t['avg_rating'] = round(sum(R) / n, 1)
        else:
            t['avg_rating'] = 0

    # ---------------- SEARCH FILTER ----------------
    if search_term:
        L = [
            t for t in L
            if search_term in t['name'].lower()
            or search_term in t['department'].lower()
        ]

    # ---------------- SORTING (BUBBLE SORT) ----------------
    n = len(L)

    for i in range(n):
        for j in range(n - i - 1):

            a = L[j]
            b = L[j + 1]

            # FIXED LOGIC (Python form)
            C = (
                (sort_by == 'alphabet' and a['name'] > b['name']) or
                (sort_by == 'highest' and a['avg_rating'] < b['avg_rating']) or
                (sort_by == 'lowest' and a['avg_rating'] > b['avg_rating'])
            )

            if C:
                L[j], L[j + 1] = b, a

    # ---------------- OUTPUT ----------------
    return render_template('teachers.html', teachers=L)


# ===================== LOGOUT =====================
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect('/login')


# ===================== TEACHER INFO =====================
@app.route('/teacher/<int:teacher_id>')
def teacher_info(teacher_id):
    if 'student_id' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM teachers WHERE id=%s", (teacher_id,))
    teacher = cursor.fetchone()

    cursor.close()
    db.close()

    if not teacher or teacher['status'] != 'active':
        flash("This teacher is not available!", "error")
        return redirect('/teachers')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT rating FROM reviews WHERE teacher_id=%s", (teacher_id,))
    ratings = [r['rating'] for r in cursor.fetchall()]

    cursor.close()
    db.close()

    avg_rating = round(sum(ratings)/len(ratings), 2) if ratings else "Not rated yet"

    return render_template('teacher_info.html', teacher=teacher, avg_rating=avg_rating)


# ===================== REVIEW =====================
@app.route('/review/<int:teacher_id>', methods=['GET', 'POST'])
def review(teacher_id):
    if 'student_id' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM teachers WHERE id=%s", (teacher_id,))
    teacher = cursor.fetchone()

    cursor.close()
    db.close()

    if not teacher or teacher['status'] != 'active':
        flash("Inactive teacher!", "error")
        return redirect('/teachers')

    if request.method == 'POST':
        rating = int(request.form['rating'])
        review_text = request.form['review_text']

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO reviews (student_id, teacher_id, department, rating, review_text, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            session['student_id'],
            teacher_id,
            session.get('student_department'),
            rating,
            review_text,
            datetime.now()
        ))

        db.commit()
        cursor.close()
        db.close()

        return render_template('review.html', success=True, show_form=False, teacher=teacher)

    return render_template(
        'review.html',
        teacher=teacher,
        show_form=True,
        student_name=session.get('student_name'),
        student_department=session.get('student_department')
    )
    
@app.route('/review', methods=['GET'])
def review_home():
    if 'student_id' not in session:
        return redirect('/login')

    return render_template(
        'review.html',
        show_form=False,
        message="First select a teacher to give your review"
    )

# ===================== REVIEW HISTORY =====================
@app.route('/history')
def history():
    if 'student_id' not in session:
        return redirect('/login')

    sort_by = request.args.get('sort', 'highest')  # ⭐ NEW

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT r.review_text, r.rating, r.created_at, t.name AS teacher_name
        FROM reviews r
        JOIN teachers t ON r.teacher_id = t.id
        WHERE r.student_id=%s
        ORDER BY r.created_at DESC
    """, (session['student_id'],))

    reviews = cursor.fetchall()

    cursor.close()
    db.close()

    # =====================================================
    # 🔢 SORTING ALGORITHM (BUBBLE SORT - SAME STYLE AS YOUR PROJECT)
    # =====================================================
    n = len(reviews)

    for i in range(n):
        for j in range(0, n - i - 1):
            a = reviews[j]
            b = reviews[j + 1]

            if sort_by == 'highest' and a['rating'] < b['rating']:
                reviews[j], reviews[j + 1] = b, a

            elif sort_by == 'lowest' and a['rating'] > b['rating']:
                reviews[j], reviews[j + 1] = b, a

            elif sort_by == 'alphabet' and a['teacher_name'].lower() > b['teacher_name'].lower():
                reviews[j], reviews[j + 1] = b, a

    return render_template('history.html', reviews=reviews, sort_by=sort_by)


# ===================== RUN =====================
if __name__ == "__main__":
    os.makedirs('static/images', exist_ok=True)
    app.run(debug=True)
