from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key"

DATABASE = "database.db"
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------- UTILITY ---------------- #

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- DATABASE INIT ---------------- #

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS students(
            student_id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT UNIQUE,
            name TEXT,
            class TEXT,
            father_name TEXT,
            mother_name TEXT,
            dob TEXT,
            photo TEXT,
            result_date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS subjects(
            subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name TEXT,
            subject_code TEXT UNIQUE,
            credit INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS marks(
            mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject_id INTEGER,
            internal INTEGER,
            theory INTEGER,
            total INTEGER,
            grade TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS re_requests(
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject_id INTEGER,
            type TEXT,
            status TEXT DEFAULT 'Pending',
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ---------------- GRADE LOGIC ---------------- #

def calculate_grade(total):
    if total >= 90: return "S+"
    elif total >= 85: return "S"
    elif total >= 80: return "O++"
    elif total >= 75: return "O+"
    elif total >= 70: return "O"
    elif total >= 65: return "A++"
    elif total >= 60: return "A+"
    elif total >= 55: return "A"
    elif total >= 50: return "B+"
    elif total >= 45: return "B"
    elif total >= 40: return "C"
    else: return "F"


# ---------------- HOME ---------------- #

@app.route("/")
def home():
    return render_template("home.html")


# ---------------- ADMIN LOGIN ---------------- #

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "admin123":
            session["admin"] = True
            flash("Login Successful", "success")
            return redirect("/admin/dashboard")
        flash("Invalid Credentials", "danger")
    return render_template("admin_login.html")


# ---------------- ADMIN DASHBOARD ---------------- #

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")

    conn = get_db()
    students = conn.execute("SELECT * FROM students").fetchall()
    subjects = conn.execute("SELECT * FROM subjects").fetchall()

    requests = conn.execute("""
    SELECT re_requests.request_id,
           students.name,
           students.roll_no,
           subjects.subject_name,
           re_requests.type,
           re_requests.status,
           re_requests.request_date
    FROM re_requests
    JOIN students ON re_requests.student_id = students.student_id
    JOIN subjects ON re_requests.subject_id = subjects.subject_id
    WHERE re_requests.status='Pending'   -- sirf pending requests
    ORDER BY request_date DESC
""").fetchall()
    

    pending_count = conn.execute(
        "SELECT COUNT(*) FROM re_requests WHERE status='Pending'"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        students=students,
        subjects=subjects,
        requests=requests,
        pending_count=pending_count
    )


# ---------------- UPDATE REQUEST STATUS ---------------- #

@app.route("/admin/update_request/<int:request_id>/<string:new_status>")
def update_request(request_id, new_status):
    if not session.get("admin"):
        return redirect("/admin")

    conn = get_db()

    # Request fetch karo
    request_row = conn.execute(
        "SELECT student_id, type FROM re_requests WHERE request_id=?",
        (request_id,)
    ).fetchone()

    if request_row:
        student_id = request_row["student_id"]
        request_type = request_row["type"]

        # Status update
        conn.execute(
            "UPDATE re_requests SET status=? WHERE request_id=?",
            (new_status, request_id)
        )
        conn.commit()

        # Notification for admin (flash)
        flash(f"Request for {request_type} {new_status} successfully!", "success")

        # Optional: Email notification (agar email field ho)
        # student_email = conn.execute("SELECT email FROM students WHERE student_id=?", (student_id,)).fetchone()["email"]
        # send_email(subject=f"{request_type} request {new_status}",
        #            recipient=student_email,
        #            body=f"Your {request_type} request has been {new_status} by admin.")

    conn.close()
    return redirect("/admin/dashboard")

# ---------------- ADD STUDENT ---------------- #

@app.route("/admin/add_student", methods=["GET", "POST"])
def add_student():
    if not session.get("admin"):
        return redirect("/admin")

    if request.method == "POST":
        photo = request.files.get("photo")
        filename = None

        if photo and allowed_file(photo.filename):
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        conn = get_db()
        conn.execute("""
            INSERT INTO students
            (roll_no,name,class,father_name,mother_name,dob,photo)
            VALUES (?,?,?,?,?,?,?)
        """, (
            request.form["roll_no"],
            request.form["name"],
            request.form["class"],
            request.form["father_name"],
            request.form["mother_name"],
            request.form["dob"],
            filename
        ))

        conn.commit()
        conn.close()

        flash("Student Added", "success")
        return redirect("/admin/dashboard")

    return render_template("add_student.html")


# ---------------- ADD SUBJECT ---------------- #

@app.route("/admin/add_subject", methods=["GET", "POST"])
def add_subject():
    if not session.get("admin"):
        return redirect("/admin")

    if request.method == "POST":
        conn = get_db()
        conn.execute("""
            INSERT INTO subjects(subject_name,subject_code,credit)
            VALUES(?,?,?)
        """, (
            request.form["subject_name"],
            request.form["subject_code"],
            request.form["credit"]
        ))
        conn.commit()
        conn.close()

        flash("Subject Added", "success")
        return redirect("/admin/dashboard")

    return render_template("add_subject.html")

# ---------------- UPLOAD MARKS WITH VALIDATION ---------------- #

@app.route("/admin/upload_marks", methods=["GET", "POST"])
def upload_marks():
    if not session.get("admin"):
        return redirect("/admin")

    conn = get_db()
    students = conn.execute("SELECT * FROM students").fetchall()
    subjects = conn.execute("SELECT * FROM subjects").fetchall()

    if request.method == "POST":
        student_id = request.form["student_id"]

        # Validate first
        for sub in subjects:
            internal = int(request.form.get(f"internal_{sub['subject_id']}", 0))
            theory = int(request.form.get(f"theory_{sub['subject_id']}", 0))

            if internal < 0 or internal > 30:
                flash("Internal marks must be between 0 and 30", "danger")
                conn.close()
                return redirect("/admin/upload_marks")

            if theory < 0 or theory > 70:
                flash("External marks must be between 0 and 70", "danger")
                conn.close()
                return redirect("/admin/upload_marks")

        conn.execute("DELETE FROM marks WHERE student_id=?", (student_id,))

        for sub in subjects:
            internal = int(request.form.get(f"internal_{sub['subject_id']}", 0))
            theory = int(request.form.get(f"theory_{sub['subject_id']}", 0))

            if theory < 28:
                total = None
                grade = "F"
            else:
                total = internal + theory
                grade = calculate_grade(total)

            conn.execute("""
                INSERT INTO marks
                (student_id,subject_id,internal,theory,total,grade)
                VALUES(?,?,?,?,?,?)
            """, (student_id, sub["subject_id"],
                  internal, theory, total, grade))

        conn.commit()
        conn.close()
        flash("Marks Uploaded Successfully!", "success")
        return redirect("/admin/dashboard")

    conn.close()
    return render_template("upload_marks.html",
                           students=students,
                           subjects=subjects)
# ---------------- DELETE STUDENT ---------------- #

@app.route("/admin/delete_student/<int:id>")
def delete_student(id):
    if not session.get("admin"):
        return redirect("/admin")

    conn = get_db()
    conn.execute("DELETE FROM marks WHERE student_id=?", (id,))
    conn.execute("DELETE FROM students WHERE student_id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin/dashboard")


# ---------------- DELETE MARKS ---------------- #

@app.route("/admin/delete_marks/<int:student_id>")
def delete_marks(student_id):
    if not session.get("admin"):
        return redirect("/admin")

    conn = get_db()
    conn.execute("DELETE FROM marks WHERE student_id=?", (student_id,))
    conn.commit()
    conn.close()

    return redirect("/admin/dashboard")


# ---------------- STUDENT LOGIN ---------------- #

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        conn = get_db()
        student = conn.execute(
            "SELECT * FROM students WHERE roll_no=? AND name=?",
            (request.form["roll_no"], request.form["name"])
        ).fetchone()
        conn.close()

        if student:
            session["student_id"] = student["student_id"]
            return redirect("/student/dashboard")

        flash("Invalid Login", "danger")

    return render_template("student_login.html")
# ---------------- EDIT MARKS WITH VALIDATION ---------------- #
@app.route("/admin/edit_marks/<int:student_id>", methods=["GET", "POST"])
def edit_marks(student_id):
    if not session.get("admin"):
        return redirect("/admin")

    conn = get_db()

    # Student Details
    student = conn.execute(
        "SELECT * FROM students WHERE student_id=?",
        (student_id,)
    ).fetchone()

    subjects = conn.execute("SELECT * FROM subjects").fetchall()

    # Old Marks
    marks_data = conn.execute(
        "SELECT * FROM marks WHERE student_id=?",
        (student_id,)
    ).fetchall()

    existing_marks = {}
    for m in marks_data:
        existing_marks[m["subject_id"]] = {
            "internal": m["internal"],
            "theory": m["theory"]
        }

    # 🔥 Approved reevaluation subjects
    approved_subjects = conn.execute("""
        SELECT subject_id 
        FROM re_requests 
        WHERE student_id=? AND status='Approved'
    """, (student_id,)).fetchall()
    approved_subject_ids = {s['subject_id'] for s in approved_subjects}

    if request.method == "POST":
        for subject in subjects:
            if subject["subject_id"] not in approved_subject_ids:
                continue  # Skip unapproved subjects

            internal = int(request.form.get(f"internal_{subject['subject_id']}", 0))
            theory = int(request.form.get(f"theory_{subject['subject_id']}", 0))

            # Validation
            if internal < 0 or internal > 30 or theory < 0 or theory > 70:
                flash("Marks out of range", "danger")
                conn.close()
                return redirect(f"/admin/edit_marks/{student_id}")

            total = internal + theory
            grade = calculate_grade(total)

            # Update marks
            conn.execute("""
                UPDATE marks
                SET internal=?, theory=?, total=?, grade=?
                WHERE student_id=? AND subject_id=?
            """, (internal, theory, total, grade, student_id, subject["subject_id"]))

        conn.commit()
        conn.close()

        flash("Marks updated successfully!", "success")
        return redirect("/admin/dashboard")

    conn.close()

    return render_template(
        "edit_marks.html",
        student=student,
        subjects=subjects,
        existing_marks=existing_marks,
        approved_subject_ids=approved_subject_ids   # Important
    )


# ---------------- STUDENT DASHBOARD ---------------- #

@app.route("/student/dashboard")
def student_dashboard():

    if not session.get("student_id"):
        return redirect("/student/login")

    student_id = session["student_id"]
    conn = get_db()

    # Get Student Details
    student = conn.execute(
        "SELECT * FROM students WHERE student_id=?",
        (student_id,)
    ).fetchone()

    # Get Marks + Subject Info
    marks = conn.execute("""
        SELECT subjects.subject_id,
               subjects.subject_name,
               subjects.credit,
               marks.internal,
               marks.theory,
               marks.total,
               marks.grade
        FROM marks
        JOIN subjects
        ON marks.subject_id = subjects.subject_id
        WHERE marks.student_id=?
    """, (student_id,)).fetchall()

    # Grade Points Mapping
    grade_points = {
        "S+": 10,
        "S": 9.5,
        "O++": 9,
        "O+": 8.5,
        "O": 8,
        "A++": 7.5,
        "A+": 7,
        "A": 6.5,
        "B+": 6,
        "B": 5.5,
        "C": 5,
        "F": 0
    }

    # 🔥 Check if any subject failed
    has_fail = any(m["grade"] == "F" for m in marks)

    total_credits = sum(m["credit"] for m in marks)
    total_points = sum(
        m["credit"] * grade_points.get(m["grade"], 0)
        for m in marks
    )

    if has_fail:
        sgpa = "-"
        overall = "FAIL"
        overall_grade = "-"
    else:
        sgpa = round(total_points / total_credits, 2) if total_credits else 0
        overall = "PASS"

        # 🔥 Overall Grade Based On SGPA
        if sgpa >= 9:
            overall_grade = "S"
        elif sgpa >= 8:
            overall_grade = "O"
        elif sgpa >= 7:
            overall_grade = "A"
        elif sgpa >= 6:
            overall_grade = "B"
        elif sgpa >= 5:
            overall_grade = "C"
        else:
            overall_grade = "F"

    conn.close()

    return render_template(
        "student_dashboard.html",
        student=student,
        marks=marks,
        sgpa=sgpa,
        overall=overall,
        overall_grade=overall_grade
    )
# ---------------- STUDENT REQUEST ---------------- #

@app.route("/student/request/<int:subject_id>/<string:req_type>")
def student_request(subject_id, req_type):
    if not session.get("student_id"):
        return redirect("/student/login")

    conn = get_db()
    conn.execute("""
        INSERT INTO re_requests(student_id,subject_id,type)
        VALUES(?,?,?)
    """, (session["student_id"], subject_id, req_type))

    conn.commit()
    conn.close()

    return redirect("/student/dashboard")


# ---------------- LOGOUT ---------------- #

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    init_db()
    app.run(debug=True)