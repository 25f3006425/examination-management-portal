from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file, Response
from database import db
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
from sqlalchemy import or_
import models
from models import (
    User, Course, Examination, ExaminationSlot, Booking,
    ExaminationRubric, Evaluation, ExaminerProfile, EvaluationMark,
    StudentProfile, CourseResource, Notification, Announcement
)
from pdf_generator import generate_result_pdf
import csv
import io


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///examination.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "zxcvbnmlkjhgfdsaqwertyuiop"

db.init_app(app)

with app.app_context():
    db.create_all()


# Helper to send in-app notification to a user
def notify_user(user_id, title, message, category="info"):
    try:
        notif = Notification(user_id=user_id, title=title, message=message, category=category)
        db.session.add(notif)
        db.session.commit()
        return notif
    except Exception:
        db.session.rollback()


# Helper to broadcast in-app notification to users
def notify_all(title, message, role="All", category="announcement"):
    try:
        query = User.query.filter_by(is_active=True)
        if role and role != "All":
            query = query.filter_by(role=role)
        users = query.all()
        for u in users:
            db.session.add(Notification(user_id=u.id, title=title, message=message, category=category))
        db.session.commit()
    except Exception:
        db.session.rollback()


# Global Jinja Context Processor (e.g. unread notifications)
@app.context_processor
def inject_global_data():
    unread_count = 0
    if "user_id" in session:
        try:
            unread_count = Notification.query.filter_by(
                user_id=session["user_id"], is_read=False
            ).count()
        except Exception:
            pass
    return dict(unread_notifications_count=unread_count)


# Function to check user role
def role_required(required_role):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            # Check whether user is logged in
            if "user_id" not in session:
                return redirect(url_for("login"))

            # Get current user from database
            user = User.query.get(session["user_id"])
            if user is None or not user.is_active:
                session.clear()
                return redirect(url_for("login"))

            # Check whether user has the required role
            if user.role != required_role:
                abort(403)

            # Check examiner approval
            if user.role == "Examiner" and not user.is_approved:
                session.clear()
                return redirect(url_for("login"))

            return function(*args, **kwargs)

        return wrapper

    return decorator


def update_examination_status(examination):
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if examination.status == "Completed":
        return

    # Check automated timeline windows
    slot_in_window = False
    if examination.slot_creation_start and examination.slot_creation_end:
        slot_in_window = (examination.slot_creation_start <= now <= examination.slot_creation_end)

    booking_in_window = False
    if examination.booking_start and examination.booking_end:
        booking_in_window = (examination.booking_start <= now <= examination.booking_end)

    # 1. Slot creation state: Override vs Timeline
    if examination.slot_creation_override == "open":
        examination.slot_creation_open = True
    elif examination.slot_creation_override == "closed":
        examination.slot_creation_open = False
    else:
        examination.slot_creation_open = slot_in_window

    # 2. Booking state: Override vs Timeline
    if examination.booking_override == "open":
        examination.booking_open = True
    elif examination.booking_override == "closed":
        examination.booking_open = False
    else:
        examination.booking_open = booking_in_window

    # 3. Overall Status
    if examination.booking_open:
        examination.status = "Booking Open"
    elif examination.slot_creation_open:
        examination.status = "Slot Creation"
    elif examination.booking_end and now > examination.booking_end:
        if examination.slots:
            all_done = True
            for slot in examination.slots:
                if slot.date >= today:
                    all_done = False
                    break
                for booking in slot.bookings:
                    if booking.status not in ["Completed", "Cancelled"]:
                        all_done = False
                        break
            if all_done:
                examination.status = "Completed"
            else:
                examination.status = "Closed"
        else:
            examination.status = "Closed"
    elif examination.slot_creation_start and now < examination.slot_creation_start:
        examination.status = "Upcoming"
    else:
        examination.status = "Draft"

    db.session.commit()


def refresh_all_examinations():
    try:
        exams = Examination.query.all()
        for ex in exams:
            update_examination_status(ex)
    except Exception:
        db.session.rollback()


# Root redirect
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("user_role")
    if role == "Admin":
        return redirect(url_for("admin_dashboard"))
    elif role == "Examiner":
        return redirect(url_for("examiner_dashboard"))
    elif role == "Student":
        return redirect(url_for("student_dashboard"))
    return redirect(url_for("login"))

# Student Registration
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        # Check whether email already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("Email already registered!")
            return redirect(url_for("register"))

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Create new student
        new_user = User(
            name=name,
            email=email,
            password_hash=hashed_password,
            role="Student"
        )

        new_user.is_approved = True

        # Save student in database
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please login.")

        return redirect(url_for("login"))

    return render_template("register.html")

# Examiner Registration
@app.route("/examiner_register", methods=["GET", "POST"])
def examiner_register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        # Check whether email already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("Email already registered!")
            return redirect(url_for("examiner_register"))

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Create new examiner
        new_examiner = User(
            name=name,
            email=email,
            password_hash=hashed_password,
            role="Examiner"
        )

        # Examiner needs Admin approval
        new_examiner.is_approved = False

        # Save examiner in database
        db.session.add(new_examiner)
        db.session.commit()

        flash("Registration successful! Wait for Admin approval.")

        return redirect(url_for("examiner_register"))

    return render_template("examiner_register.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        # Find user using email or student roll number
        user = User.query.filter_by(email=email).first()
        if not user and email:
            sp = StudentProfile.query.filter_by(roll_number=email.strip().upper()).first()
            if sp:
                user = sp.user

        # Check whether user exists and password is correct
        if user and check_password_hash(user.password_hash, password):
            
            # Check whether account is active
            if not user.is_active:
                flash("Your account has been deactivated.")
                return redirect(url_for("login"))

            # Check whether examiner is approved
            if user.role == "Examiner" and not user.is_approved:
                flash("Your account is waiting for Admin approval.")
                return redirect(url_for("login"))

            # Store user information in session
            session["user_id"] = user.id
            session["user_role"] = user.role
            session["user_name"] = user.name

            flash("Login successful!")

            # Redirect according to role
            if user.role == "Admin":
                return redirect(url_for("admin_dashboard"))

            elif user.role == "Examiner":
                return redirect(url_for("examiner_dashboard"))

            elif user.role == "Student":
                return redirect(url_for("student_dashboard"))

        else:
            flash("Invalid email or password!")

    return render_template("login.html")

# Admin Dashboard
@app.route("/admin_dashboard")
@role_required("Admin")
def admin_dashboard():

    # Dashboard statistics
    total_courses = Course.query.count()
    total_examinations = Examination.query.count()
    total_examiners = User.query.filter_by(role="Examiner").count()
    total_students = User.query.filter_by(role="Student").count()
    total_slots = ExaminationSlot.query.count()
    total_bookings = Booking.query.count()

    # Get pending examiners
    pending_examiners = User.query.filter_by(
        role="Examiner",
        is_approved=False
    ).all()

    # Get approved and active examiners
    approved_examiners = User.query.filter_by(
        role="Examiner",
        is_approved=True,
        is_active=True
    ).all()

    # Get deactivated examiners
    inactive_examiners = User.query.filter_by(
        role="Examiner",
        is_active=False
    ).all()

    return render_template(
        "admin_dashboard.html",
        total_courses=total_courses,
        total_examinations=total_examinations,
        total_examiners=total_examiners,
        total_students=total_students,
        total_slots=total_slots,
        total_bookings=total_bookings,
        pending_examiners=pending_examiners,
        approved_examiners=approved_examiners,
        inactive_examiners=inactive_examiners
    )

# Examiner Dashboard
@app.route("/examiner_dashboard")
@role_required("Examiner")
def examiner_dashboard():

    examiner_id = session["user_id"]

    # Get all slots created by this examiner
    slots = ExaminationSlot.query.filter_by(
        examiner_id=examiner_id
    ).all()

    # Get assigned examinations
    examinations = set()

    for slot in slots:
        examinations.add(slot.examination_id)

    total_examinations = len(examinations)

    # Count created slots
    total_slots = len(slots)

    # Count students booked
    total_bookings = 0

    for slot in slots:
        total_bookings += Booking.query.filter_by(
            slot_id=slot.id,
            status="Booked"
        ).count()

# Count pending evaluations
    pending_evaluations = 0

    for slot in slots:

        bookings = Booking.query.filter_by(
            slot_id=slot.id,
            status="Booked"
        ).all()

        for booking in bookings:

            evaluation = Evaluation.query.filter_by(
                booking_id=booking.id
            ).first()

            if evaluation is None or evaluation.status == "Pending":
                pending_evaluations += 1    

    announcements = Announcement.query.filter(
        or_(Announcement.target_role == "All", Announcement.target_role == "Examiner")
    ).order_by(Announcement.id.desc()).limit(3).all()

    return render_template(
        "examiner_dashboard.html",
        examiner=User.query.get(examiner_id),
        total_examinations=total_examinations,
        total_slots=total_slots,
        total_bookings=total_bookings,
        pending_evaluations=pending_evaluations,
        announcements=announcements
    )
# Student Dashboard
@app.route("/student_dashboard")
@role_required("Student")
def student_dashboard():

    refresh_all_examinations()
    student_id = session["user_id"]
    student = User.query.get_or_404(student_id)

    # Get all bookings of this student
    all_bookings = Booking.query.filter_by(
        student_id=student_id
    ).all()

    total_bookings = len(all_bookings)

    upcoming_bookings = [
        b for b in all_bookings
        if b.status == "Booked" and b.slot.date >= date.today().isoformat()
    ]
    upcoming_examinations = len(upcoming_bookings)
    completed_examinations = len([b for b in all_bookings if b.status == "Completed"])

    # Completed Evaluations for Results
    evaluations = Evaluation.query.join(Booking).filter(
        Booking.student_id == student_id,
        Evaluation.status == "Completed"
    ).order_by(Evaluation.id.desc()).all()

    current_results = evaluations[:3]
    previous_results = evaluations[3:]

    marks_list = [ev.marks for ev in evaluations if ev.marks is not None]
    avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
    highest_marks = max(marks_list) if marks_list else 0

    announcements = Announcement.query.filter(
        or_(Announcement.target_role == "All", Announcement.target_role == "Student")
    ).order_by(Announcement.id.desc()).limit(3).all()

    courses = Course.query.all()

    return render_template(
        "student_dashboard.html",
        student=student,
        total_bookings=total_bookings,
        upcoming_examinations=upcoming_examinations,
        completed_examinations=completed_examinations,
        upcoming_bookings=upcoming_bookings,
        all_results=evaluations,
        current_results=current_results,
        previous_results=previous_results,
        avg_marks=avg_marks,
        highest_marks=highest_marks,
        announcements=announcements,
        courses=courses
    )

# Logout
@app.route("/logout")
def logout():

    # Clear all session information
    session.clear()

    flash("You have been logged out successfully.")

    # Redirect to login page
    return redirect(url_for("login"))

# Approve Examiner
@app.route("/approve_examiner/<int:user_id>", methods=["POST"])
@role_required("Admin")
def approve_examiner(user_id):

    examiner = User.query.filter_by(
        id=user_id,
        role="Examiner"
    ).first_or_404()

    examiner.is_approved = True
    db.session.commit()

    flash("Examiner approved successfully!")

    return redirect(url_for("admin_dashboard"))


# Deactivate Examiner
@app.route("/deactivate_examiner/<int:user_id>", methods=["POST"])
@role_required("Admin")
def deactivate_examiner(user_id):

    examiner = User.query.filter_by(
        id=user_id,
        role="Examiner"
    ).first_or_404()

    examiner.is_active = False
    db.session.commit()

    flash("Examiner deactivated successfully!")

    return redirect(url_for("admin_dashboard"))


# Reactivate Examiner
@app.route("/reactivate_examiner/<int:user_id>", methods=["POST"])
@role_required("Admin")
def reactivate_examiner(user_id):

    examiner = User.query.filter_by(
        id=user_id,
        role="Examiner"
    ).first_or_404()

    examiner.is_active = True
    db.session.commit()

    flash("Examiner reactivated successfully!")

    return redirect(url_for("admin_dashboard"))

@app.route("/courses")
@role_required("Admin")
def courses():
    all_courses = Course.query.all()

    return render_template("courses.html", courses=all_courses)

@app.route("/course/add", methods=["GET", "POST"])
@role_required("Admin")
def add_course():

    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")

        if not name or not name.strip():
            flash("Course name is required.")
            return redirect(url_for("add_course"))

        new_course = Course(
            name=name.strip(),
            description=description
        )

        db.session.add(new_course)
        db.session.commit()

        # Optional initial course resource
        res_title = request.form.get("resource_title")
        res_url = request.form.get("resource_url")
        if res_title and res_title.strip() and res_url and res_url.strip():
            res = CourseResource(
                course_id=new_course.id,
                title=res_title.strip(),
                url=res_url.strip()
            )
            db.session.add(res)
            db.session.commit()

        flash("Course added successfully.")
        return redirect(url_for("courses"))

    return render_template("add_course.html")

@app.route("/course/edit/<int:course_id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_course(course_id):

    course = Course.query.get_or_404(course_id)

    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")

        if not name or not name.strip():
            flash("Course name is required.")
            return redirect(url_for("edit_course", course_id=course.id))

        course.name = name.strip()
        course.description = description

        db.session.commit()

        flash("Course updated successfully.")
        return redirect(url_for("courses"))

    return render_template("edit_course.html", course=course)

@app.route("/course/delete/<int:course_id>", methods=["POST"])
@role_required("Admin")
def delete_course(course_id):

    course = Course.query.get_or_404(course_id)

    if course.examinations:
        flash("Cannot delete this course because examinations are linked to it.")
        return redirect(url_for("courses"))

    db.session.delete(course)
    db.session.commit()

    flash("Course deleted successfully.")
    return redirect(url_for("courses"))

@app.route("/examinations")
@role_required("Admin")
def examinations():

    search = request.args.get("search", "").strip().lower()

    all_examinations = Examination.query.all()

    for examination in all_examinations:
        update_examination_status(examination)

    if search:
        all_examinations = [
            examination for examination in all_examinations
            if search in str(examination.id)
            or search in examination.name.lower()
            or search in examination.course.name.lower()
        ]

    return render_template(
        "examinations.html",
        examinations=all_examinations,
        search=search
    )

@app.route("/examination/add", methods=["GET", "POST"])
@role_required("Admin")
def add_examination():

    all_courses = Course.query.all()

    if request.method == "POST":

        name = request.form.get("name")
        course_id = request.form.get("course_id", type=int)

        if not name or not name.strip():
            flash("Examination name is required.")
            return redirect(url_for("add_examination"))

        course = Course.query.get(course_id)

        if course is None:
            flash("Please select a valid course.")
            return redirect(url_for("add_examination"))

        new_examination = Examination(
            name=name.strip(),
            course_id=course_id
        )

        db.session.add(new_examination)
        db.session.commit()

        flash("Examination added successfully.")
        return redirect(url_for("examinations"))

    return render_template(
        "add_examination.html",
        courses=all_courses
    )

@app.route("/examination/edit/<int:examination_id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_examination(examination_id):

    examination = Examination.query.get_or_404(examination_id)
    all_courses = Course.query.all()

    if request.method == "POST":

        name = request.form.get("name")
        course_id = request.form.get("course_id", type=int)

        if not name or not name.strip():
            flash("Examination name is required.")
            return redirect(
                url_for("edit_examination", examination_id=examination.id)
            )

        course = Course.query.get(course_id)

        if course is None:
            flash("Please select a valid course.")
            return redirect(
                url_for("edit_examination", examination_id=examination.id)
            )

        examination.name = name.strip()
        examination.course_id = course_id

        db.session.commit()

        flash("Examination updated successfully.")
        return redirect(url_for("examinations"))

    return render_template(
        "edit_examination.html",
        examination=examination,
        courses=all_courses
    )

@app.route("/examination/delete/<int:examination_id>", methods=["POST"])
@role_required("Admin")
def delete_examination(examination_id):

    examination = Examination.query.get_or_404(examination_id)

    if examination.slots or examination.rubrics:
        flash("Cannot delete an examination with linked slots or rubrics.")
        return redirect(url_for("examinations"))

    db.session.delete(examination)
    db.session.commit()

    flash("Examination deleted successfully.")
    return redirect(url_for("examinations"))

@app.route("/examination/<int:examination_id>/rubrics")
@role_required("Admin")
def manage_rubrics(examination_id):

    examination = Examination.query.get_or_404(examination_id)

    rubrics = ExaminationRubric.query.filter_by(
        examination_id=examination_id
    ).all()

    total_marks = sum(rubric.marks for rubric in rubrics)

    return render_template(
        "rubrics.html",
        examination=examination,
        rubrics=rubrics,
        total_marks=total_marks
    )

@app.route("/rubric/add/<int:examination_id>", methods=["GET", "POST"])
@role_required("Admin")
def add_rubric(examination_id):

    examination = Examination.query.get_or_404(examination_id)

    if request.method == "POST":

        criterion = request.form.get("criterion")
        marks = request.form.get("marks", type=int)

        if not criterion or not criterion.strip():
            flash("Criterion name is required.")
            return redirect(url_for("add_rubric", examination_id=examination_id))

        if marks is None or marks <= 0:
            flash("Marks must be a positive number.")
            return redirect(url_for("add_rubric", examination_id=examination_id))

        new_rubric = ExaminationRubric(
            examination_id=examination_id,
            criterion=criterion.strip(),
            marks=marks
        )

        db.session.add(new_rubric)
        db.session.commit()

        flash("Rubric added successfully.")
        return redirect(url_for("manage_rubrics", examination_id=examination_id))

    return render_template(
        "add_rubric.html",
        examination=examination
    )

@app.route("/rubric/edit/<int:rubric_id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_rubric(rubric_id):

    rubric = ExaminationRubric.query.get_or_404(rubric_id)

    if request.method == "POST":

        criterion = request.form.get("criterion")
        marks = request.form.get("marks", type=int)

        if not criterion or not criterion.strip():
            flash("Criterion name is required.")
            return redirect(url_for("edit_rubric", rubric_id=rubric.id))

        if marks is None or marks <= 0:
            flash("Marks must be a positive number.")
            return redirect(url_for("edit_rubric", rubric_id=rubric.id))

        rubric.criterion = criterion.strip()
        rubric.marks = marks

        db.session.commit()

        flash("Rubric updated successfully.")

        return redirect(
            url_for("manage_rubrics", examination_id=rubric.examination_id)
        )

    return render_template("edit_rubric.html", rubric=rubric)

@app.route("/rubric/delete/<int:rubric_id>", methods=["POST"])
@role_required("Admin")
def delete_rubric(rubric_id):

    rubric = ExaminationRubric.query.get_or_404(rubric_id)

    examination_id = rubric.examination_id

    db.session.delete(rubric)
    db.session.commit()

    flash("Rubric deleted successfully.")

    return redirect(
        url_for("manage_rubrics", examination_id=examination_id)
    )

@app.route("/examination/<int:examination_id>/settings", methods=["GET", "POST"])
@role_required("Admin")
def examination_settings(examination_id):

    examination = Examination.query.get_or_404(examination_id)

    if request.method == "POST":

        slot_start = request.form.get("slot_creation_start")
        slot_end = request.form.get("slot_creation_end")
        booking_start = request.form.get("booking_start")
        booking_end = request.form.get("booking_end")

        # Check slot creation dates
        if bool(slot_start) != bool(slot_end):
            flash("Enter both slot creation dates.")
            return redirect(url_for(
                "examination_settings",
                examination_id=examination.id
            ))

        if slot_start and slot_start > slot_end:
            flash("Slot creation end must be after its start.")
            return redirect(url_for(
                "examination_settings",
                examination_id=examination.id
            ))

        # Check booking dates
        if bool(booking_start) != bool(booking_end):
            flash("Enter both booking dates.")
            return redirect(url_for(
                "examination_settings",
                examination_id=examination.id
            ))

        if booking_start and booking_start > booking_end:
            flash("Booking end must be after its start.")
            return redirect(url_for(
                "examination_settings",
                examination_id=examination.id
            ))

        # Constraint: Slot booking should only start AFTER slot creation time ends
        if slot_end and booking_start and booking_start < slot_end:
            flash(f"Constraint Violation: Slot booking can only start AFTER slot creation time ends (Slot Creation End: {slot_end.replace('T', ' ')}).", "danger")
            return redirect(url_for(
                "examination_settings",
                examination_id=examination.id
            ))

        examination.slot_creation_start = slot_start or None
        examination.slot_creation_end = slot_end or None
        examination.booking_start = booking_start or None
        examination.booking_end = booking_end or None

        update_examination_status(examination)

        flash("Examination timelines saved successfully.")
        return redirect(url_for(
            "examination_settings",
            examination_id=examination.id
        ))

    return render_template(
        "examination_settings.html",
        examination=examination
    )

@app.route("/examination/<int:examination_id>/toggle-slots", methods=["POST"])
@role_required("Admin")
def toggle_slot_creation(examination_id):

    examination = Examination.query.get_or_404(examination_id)

    if examination.slot_creation_open:
        examination.slot_creation_override = "closed"
        examination.slot_creation_open = False
        flash("Faculty slot creation has been stopped abruptly by Admin.", "warning")
    else:
        examination.slot_creation_override = "open"
        examination.slot_creation_open = True
        flash("Faculty slot creation has been started immediately by Admin.", "success")

    update_examination_status(examination)

    return redirect(url_for(
        "examination_settings",
        examination_id=examination.id
    ))

@app.route("/examination/<int:examination_id>/reset-slots-override", methods=["POST"])
@role_required("Admin")
def reset_slot_override(examination_id):

    examination = Examination.query.get_or_404(examination_id)
    examination.slot_creation_override = None
    update_examination_status(examination)
    flash("Slot creation schedule reset to automatic timeline.", "info")

    return redirect(url_for(
        "examination_settings",
        examination_id=examination.id
    ))

@app.route("/examination/<int:examination_id>/toggle-booking", methods=["POST"])
@role_required("Admin")
def toggle_booking(examination_id):

    examination = Examination.query.get_or_404(examination_id)

    if examination.booking_open:
        examination.booking_override = "closed"
        examination.booking_open = False
        flash("Student booking has been stopped abruptly by Admin.", "warning")
    else:
        examination.booking_override = "open"
        examination.booking_open = True
        flash("Student booking has been started immediately by Admin.", "success")

    update_examination_status(examination)

    return redirect(url_for(
        "examination_settings",
        examination_id=examination.id
    ))

@app.route("/examination/<int:examination_id>/reset-booking-override", methods=["POST"])
@role_required("Admin")
def reset_booking_override(examination_id):

    examination = Examination.query.get_or_404(examination_id)
    examination.booking_override = None
    update_examination_status(examination)
    flash("Student booking schedule reset to automatic timeline.", "info")

    return redirect(url_for(
        "examination_settings",
        examination_id=examination.id
    ))

@app.route("/admin/slots")
@role_required("Admin")
def admin_slots():

    search = request.args.get("search", "").strip()

    all_slots = ExaminationSlot.query.all()

    if search:
        all_slots = [
            slot for slot in all_slots
            if search.lower() in str(slot.id).lower()
            or search.lower() in slot.examination.name.lower()
            or search.lower() in slot.examiner.name.lower()
        ]

    approved_examiners = User.query.filter_by(
        role="Examiner",
        is_approved=True,
        is_active=True
    ).all()

    return render_template(
        "admin_slots.html",
        slots=all_slots,
        examiners=approved_examiners,
        search=search
    )

@app.route("/admin/slot/<int:slot_id>/change-examiner", methods=["POST"])
@role_required("Admin")
def change_slot_examiner(slot_id):

    slot = ExaminationSlot.query.get_or_404(slot_id)

    examiner_id = request.form.get("examiner_id", type=int)

    examiner = User.query.filter_by(
        id=examiner_id,
        role="Examiner",
        is_approved=True,
        is_active=True
    ).first()

    if examiner is None:
        flash("Please select a valid active examiner.")
        return redirect(url_for("admin_slots"))

    slot.examiner_id = examiner.id

    db.session.commit()

    flash("Examiner changed successfully.")

    return redirect(url_for("admin_slots"))

@app.route("/admin/bookings")
@role_required("Admin")
def admin_bookings():

    search = request.args.get("search", "").strip()

    all_bookings = Booking.query.all()

    if search:
        all_bookings = [
            booking for booking in all_bookings
            if search.lower() in str(booking.id).lower()
            or search.lower() in booking.student.name.lower()
            or search.lower() in booking.student.email.lower()
            or search.lower() in booking.slot.examination.name.lower()
        ]

    return render_template(
        "admin_bookings.html",
        bookings=all_bookings,
        search=search
    )

@app.route("/admin/booking/<int:booking_id>/reschedule", methods=["GET", "POST"])
@role_required("Admin")
def reschedule_booking(booking_id):

    booking = Booking.query.get_or_404(booking_id)

    # Show only slots belonging to the same examination
    available_slots = ExaminationSlot.query.filter_by(
        examination_id=booking.slot.examination_id
    ).all()

    if request.method == "POST":

        new_slot_id = request.form.get("slot_id", type=int)

        new_slot = ExaminationSlot.query.filter_by(
            id=new_slot_id,
            examination_id=booking.slot.examination_id
        ).first()

        if new_slot is None:
            flash("Please select a valid slot.")
            return redirect(
                url_for("reschedule_booking", booking_id=booking.id)
            )

        if new_slot.id == booking.slot_id:
            flash("This student is already booked in that slot.")
            return redirect(
                url_for("reschedule_booking", booking_id=booking.id)
            )


        # Only active bookings can be rescheduled
        if booking.status != "Booked":
            flash("Only active bookings can be rescheduled.")
            return redirect(url_for("admin_bookings"))

        # Prevent duplicate bookings for the same examination
        existing_booking = Booking.query.join(
            ExaminationSlot,
            Booking.slot_id == ExaminationSlot.id
        ).filter(
            Booking.student_id == booking.student_id,
            Booking.status == "Booked",
            ExaminationSlot.examination_id == booking.slot.examination_id,
            Booking.id != booking.id
        ).first()

        if existing_booking:
            flash("Student already has a booking for this examination.")
            return redirect(url_for("reschedule_booking", booking_id=booking.id))

        # Check destination slot capacity
        booked_count = Booking.query.filter_by(
            slot_id=new_slot.id,
            status="Booked"
        ).count()

        if booked_count >= new_slot.capacity:
            flash("The selected slot is already full.")
            return redirect(url_for("reschedule_booking", booking_id=booking.id))

        booking.slot_id = new_slot.id
        db.session.commit()

        # Notify student of rescheduling
        notify_user(
            booking.student_id,
            "Booking Rescheduled by Admin",
            f"Your booking for {booking.slot.examination.name} was rescheduled to {new_slot.date} at {new_slot.time}.",
            "reschedule"
        )

        flash("Booking rescheduled successfully.")
        return redirect(url_for("admin_bookings"))

    return render_template(
        "reschedule_booking.html",
        booking=booking,
        slots=available_slots
    )

@app.route("/admin/users")
@role_required("Admin")
def admin_users():

    search = request.args.get("search", "").strip().lower()

    students = User.query.filter_by(role="Student").all()
    examiners = User.query.filter_by(role="Examiner").all()

    if search:
        students = [
            student for student in students
            if search in str(student.id)
            or search in student.name.lower()
            or search in student.email.lower()
        ]

        examiners = [
            examiner for examiner in examiners
            if search in str(examiner.id)
            or search in examiner.name.lower()
            or search in examiner.email.lower()
        ]

    return render_template(
        "admin_users.html",
        students=students,
        examiners=examiners,
        search=search
    )

@app.route("/examiner/evaluate/<int:booking_id>", methods=["GET", "POST"])
@role_required("Examiner")
def evaluate_student(booking_id):

    examiner_id = session["user_id"]

    booking = Booking.query.get_or_404(booking_id)

    # Only booked students can be evaluated
    if booking.status != "Booked":
        flash("This booking cannot be evaluated.")
        return redirect(url_for("examiner_bookings"))

    # Check whether this examiner owns the slot
    if booking.slot.examiner_id != examiner_id:
        abort(403)

    rubrics = ExaminationRubric.query.filter_by(
        examination_id=booking.slot.examination_id
    ).all()

    if not rubrics:
        flash("No examination rubrics have been created.")
        return redirect(url_for("examiner_bookings"))

    evaluation = Evaluation.query.filter_by(
        booking_id=booking.id
    ).first()

    if request.method == "POST":

        total_marks = 0
        marks_list = []

        # Read marks for each rubric
        for rubric in rubrics:

            marks = request.form.get(
                "rubric_" + str(rubric.id),
                type=int
            )

            if marks is None or marks < 0 or marks > rubric.marks:
                flash("Please enter valid marks for every criterion.")
                return redirect(
                    url_for("evaluate_student", booking_id=booking.id)
                )

            total_marks += marks

            marks_list.append((rubric, marks))

        remarks = request.form.get("remarks")

        # Create evaluation if it does not exist
        if evaluation is None:

            evaluation = Evaluation(
                booking_id=booking.id,
                examiner_id=examiner_id
            )

            db.session.add(evaluation)
            db.session.flush()

        # Save total marks and remarks
        evaluation.marks = total_marks
        evaluation.remarks = remarks
        evaluation.status = "Completed"
        booking.status = "Completed"

        # Save individual rubric marks
        for rubric, marks in marks_list:

            rubric_mark = EvaluationMark.query.filter_by(
                evaluation_id=evaluation.id,
                rubric_id=rubric.id
            ).first()

            if rubric_mark is None:

                rubric_mark = EvaluationMark(
                    evaluation_id=evaluation.id,
                    rubric_id=rubric.id,
                    marks=marks
                )

                db.session.add(rubric_mark)

            else:

                rubric_mark.marks = marks

        db.session.commit()

        # Notify student about published result
        notify_user(
            booking.student_id,
            "Examination Result Published",
            f"Your evaluation for {booking.slot.examination.name} is complete. Total Marks: {total_marks}.",
            "result"
        )

        flash("Evaluation submitted successfully.")

        return redirect(url_for("examiner_bookings"))

    # Get previously submitted marks
    marks_by_rubric = {}

    if evaluation:

        saved_marks = EvaluationMark.query.filter_by(
            evaluation_id=evaluation.id
        ).all()

        for saved_mark in saved_marks:
            marks_by_rubric[saved_mark.rubric_id] = saved_mark.marks

    return render_template(
        "evaluate_student.html",
        booking=booking,
        rubrics=rubrics,
        evaluation=evaluation,
        marks_by_rubric=marks_by_rubric
    )

@app.route("/examiner/bookings")
@role_required("Examiner")
def examiner_bookings():

    examiner_id = session["user_id"]

    slots = ExaminationSlot.query.filter_by(
        examiner_id=examiner_id
    ).all()

    bookings = []

    for slot in slots:
        slot_bookings = Booking.query.filter_by(
            slot_id=slot.id,
            status="Booked"
        ).all()

        bookings.extend(slot_bookings)

    return render_template(
        "examiner_bookings.html",
        bookings=bookings
    )

@app.route("/examiner/slots", methods=["GET", "POST"])
@role_required("Examiner")
def examiner_slots():

    examiner_id = session["user_id"]

    if request.method == "POST":

        examination_id = request.form.get("examination_id", type=int)
        slot_date = request.form.get("date")
        time = request.form.get("time")

        examination = Examination.query.get(examination_id)

        if examination is None:
            flash("Please select a valid examination.")
            return redirect(url_for("examiner_slots"))

        if not examination.slot_creation_open:
            flash("Slot creation is currently closed.")
            return redirect(url_for("examiner_slots"))

        now = datetime.now().strftime("%Y-%m-%dT%H:%M")

        if not examination.slot_creation_start or not examination.slot_creation_end:
            flash("Slot creation dates are not configured.")
            return redirect(url_for("examiner_slots"))

        if now < examination.slot_creation_start or now > examination.slot_creation_end:
            flash("You can create slots only during the allowed period.")
            return redirect(url_for("examiner_slots"))

        if not slot_date or not time:
            flash("Please enter both date and time.")
            return redirect(url_for("examiner_slots"))        

        slot_datetime = f"{slot_date}T{time}"
        if slot_datetime < now:
            flash("You cannot create a slot in the past.")
            return redirect(url_for("examiner_slots"))

        new_slot = ExaminationSlot(
            examination_id=examination_id,
            examiner_id=examiner_id,
            date=slot_date,
            time=time
        )

        db.session.add(new_slot)
        db.session.commit()

        flash("Examination slot created successfully.")

        return redirect(url_for("examiner_slots"))

    examinations = Examination.query.filter_by(
        slot_creation_open=True
    ).all()

    slots = ExaminationSlot.query.filter_by(
        examiner_id=examiner_id
    ).all()

    return render_template(
        "examiner_slots.html",
        examinations=examinations,
        slots=slots
    )

@app.route("/examiner/slots/edit/<int:slot_id>", methods=["GET", "POST"])
@role_required("Examiner")
def edit_examiner_slot(slot_id):

    examiner_id = session["user_id"]

    slot = ExaminationSlot.query.get_or_404(slot_id)

    # Check slot ownership
    if slot.examiner_id != examiner_id:
        abort(403)

    # Check whether booking has started
    if slot.examination.booking_open:
        flash("You cannot edit slots after booking has started.")
        return redirect(url_for("examiner_slots"))

    # Do not change slots that already have bookings
    if Booking.query.filter_by(slot_id=slot.id).count() > 0:
        flash("This slot already has bookings and cannot be edited.")
        return redirect(url_for("examiner_slots"))

    if request.method == "POST":

        slot_date = request.form.get("date")
        time = request.form.get("time")

        if not slot_date or not time:
            flash("Please enter both date and time.")
            return redirect(url_for("edit_examiner_slot", slot_id=slot.id))

        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        slot_datetime = f"{slot_date}T{time}"
        if slot_datetime < now:
            flash("You cannot set a slot date and time in the past.")
            return redirect(url_for("edit_examiner_slot", slot_id=slot.id))

        slot.date = slot_date
        slot.time = time
        
        db.session.commit()

        flash("Slot updated successfully.")

        return redirect(url_for("examiner_slots"))

    return render_template(
        "edit_examiner_slot.html",
        slot=slot
    )

@app.route("/examiner/slots/delete/<int:slot_id>", methods=["POST"])
@role_required("Examiner")
def delete_examiner_slot(slot_id):

    examiner_id = session["user_id"]

    slot = ExaminationSlot.query.get_or_404(slot_id)

    # Check slot ownership
    if slot.examiner_id != examiner_id:
        abort(403)

    # Check whether booking has started
    if slot.examination.booking_open:
        flash("You cannot delete slots after booking has started.")
        return redirect(url_for("examiner_slots"))

    # Check whether students have already booked this slot
    if Booking.query.filter_by(slot_id=slot.id).count() > 0:
        flash("You cannot delete a slot that has bookings.")
        return redirect(url_for("examiner_slots"))

    db.session.delete(slot)
    db.session.commit()

    flash("Slot deleted successfully.")

    return redirect(url_for("examiner_slots"))

@app.route("/examiner/profile", methods=["GET", "POST"])
@role_required("Examiner")
def examiner_profile():

    examiner_id = session["user_id"]

    examiner = User.query.get_or_404(examiner_id)

    profile = ExaminerProfile.query.filter_by(
        user_id=examiner_id
    ).first()

    # Create profile if it does not exist
    if profile is None:
        profile = ExaminerProfile(user_id=examiner_id)
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":

        examiner.name = request.form.get("name")
        profile.qualification = request.form.get("qualification")
        profile.specialization = request.form.get("specialization")

        db.session.commit()

        flash("Profile updated successfully.")

        return redirect(url_for("examiner_profile"))

    return render_template(
        "examiner_profile.html",
        examiner=examiner,
        profile=profile
    )



@app.route("/examiner/examinations")
@role_required("Examiner")
def examiner_examinations():

    examiner_id = session["user_id"]

    examinations = Examination.query.join(
        ExaminationSlot
    ).filter(
        ExaminationSlot.examiner_id == examiner_id
    ).distinct().all()

    return render_template(
        "examiner_examinations.html",
        examinations=examinations
    )

@app.route("/student/profile", methods=["GET", "POST"])
@role_required("Student")
def student_profile():

    student_id = session["user_id"]
    student = User.query.get_or_404(student_id)
    profile = student.student_profile
    if not profile:
        roll = student.email.split("@")[0].upper()
        profile = StudentProfile(user_id=student_id, roll_number=roll)
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":

        name = request.form.get("name")
        phone = request.form.get("phone")
        department = request.form.get("department")
        year = request.form.get("year")
        new_password = request.form.get("new_password")

        if not name or not name.strip():
            flash("Name is required.", "danger")
            return redirect(url_for("student_profile"))

        student.name = name.strip()
        session["user_name"] = student.name

        if phone is not None:
            profile.phone = phone.strip()
        if department:
            profile.department = department.strip()
        if year:
            profile.year = year.strip()
        if new_password and new_password.strip():
            student.password_hash = generate_password_hash(new_password.strip())

        db.session.commit()

        flash("Profile updated successfully.", "success")
        return redirect(url_for("student_profile"))

    return render_template(
        "student_profile.html",
        student=student,
        profile=profile
    )

@app.route("/student/examinations")
@role_required("Student")
def student_examinations():
    search = request.args.get("search", "").strip()

    # Show examinations for which booking is open
    query = Examination.query.filter_by(booking_open=True)

    # Search by examination name or examination ID
    if search:
        if search.isdigit():
            query = query.filter(
                or_(
                    Examination.name.ilike("%" + search + "%"),
                    Examination.id == int(search)
                )
            )
        else:
            query = query.filter(
                Examination.name.ilike("%" + search + "%")
            )

    examinations = query.all()

    return render_template(
        "student_examinations.html",
        examinations=examinations,
        search=search
    )


@app.route("/student/examinations/<int:examination_id>")
@role_required("Student")
def student_examination_slots(examination_id):
    examination = Examination.query.get_or_404(examination_id)

    # Get slots belonging to this examination
    slots = ExaminationSlot.query.filter_by(
        examination_id=examination_id
    ).filter(
        ExaminationSlot.date >= date.today().isoformat()
    ).all()

    # Calculate remaining seats in each slot
    available_slots = []

    for slot in slots:
        booked_count = Booking.query.filter_by(
            slot_id=slot.id,
            status="Booked"
        ).count()

        remaining_seats = slot.capacity - booked_count

        if remaining_seats > 0:
            available_slots.append({
                "slot": slot,
                "remaining_seats": remaining_seats
            })

    return render_template(
        "student_slots.html",
        examination=examination,
        available_slots=available_slots
    )


@app.route("/student/book-slot/<int:slot_id>", methods=["POST"])
@role_required("Student")
def student_book_slot(slot_id):
    student_id = session["user_id"]

    slot = ExaminationSlot.query.get_or_404(slot_id)
    examination = Examination.query.get_or_404(slot.examination_id)

    # Check whether booking is open
    if not examination.booking_open:
        flash("Booking for this examination is closed.", "danger")
        return redirect(url_for(
            "student_examination_slots",
            examination_id=examination.id
        ))

    # Check whether the slot date has passed
    if slot.date < date.today().isoformat():
        flash("You cannot book a slot in the past.", "danger")
        return redirect(url_for(
            "student_examination_slots",
            examination_id=examination.id
        ))

    # Prevent the student from booking the same examination twice
    existing_booking = Booking.query.join(
        ExaminationSlot,
        Booking.slot_id == ExaminationSlot.id
    ).filter(
        Booking.student_id == student_id,
        Booking.status == "Booked",
        ExaminationSlot.examination_id == examination.id
    ).first()

    if existing_booking:
        flash(
            "You have already booked a slot for this examination.",
            "warning"
        )
        return redirect(url_for(
            "student_examination_slots",
            examination_id=examination.id
        ))

    # Check how many students have already booked this slot
    booked_count = Booking.query.filter_by(
        slot_id=slot.id,
        status="Booked"
    ).count()

    if booked_count >= slot.capacity:
        flash("This slot is already full.", "danger")
        return redirect(url_for(
            "student_examination_slots",
            examination_id=examination.id
        ))

    # Create the booking
    booking = Booking(
        student_id=student_id,
        slot_id=slot.id,
        status="Booked"
    )

    db.session.add(booking)
    db.session.commit()

    # Notify student of booking confirmation
    notify_user(
        student_id,
        "Booking Confirmed",
        f"Your examination slot for {examination.name} on {slot.date} at {slot.time} has been booked successfully.",
        "booking"
    )

    flash("Your examination slot has been booked successfully.", "success")

    return redirect(url_for("student_bookings"))

@app.route("/student/bookings")
@role_required("Student")
def student_bookings():
    bookings = Booking.query.filter_by(
        student_id=session["user_id"],
        status="Booked"
    ).all()

    return render_template(
        "student_bookings.html",
        bookings=bookings
    )

@app.route("/student/cancel-booking/<int:booking_id>", methods=["POST"])
@role_required("Student")
def student_cancel_booking(booking_id):

    booking = Booking.query.filter_by(
        id=booking_id,
        student_id=session["user_id"]
    ).first_or_404()

    # Only active bookings can be cancelled
    if booking.status != "Booked":
        flash("This booking cannot be cancelled.", "danger")
        return redirect(url_for("student_bookings"))

    examination = booking.slot.examination

    # Check the cancellation deadline
    if examination.booking_end:
        if date.today().isoformat() > examination.booking_end:
            flash(
                "The cancellation deadline has passed.",
                "danger"
            )
            return redirect(url_for("student_bookings"))

    # Cancel the booking
    booking.status = "Cancelled"
    db.session.commit()

    # Notify student of cancellation
    notify_user(
        session["user_id"],
        "Booking Cancelled",
        f"Your booking for {booking.slot.examination.name} on {booking.slot.date} has been cancelled.",
        "cancellation"
    )

    flash("Your booking has been cancelled successfully.", "success")

    return redirect(url_for("student_bookings"))


@app.route("/student/upcoming")
@role_required("Student")
def student_upcoming():

    bookings = Booking.query.filter_by(
        student_id=session["user_id"],
        status="Booked"
    ).all()

    upcoming_bookings = []

    for booking in bookings:
        if booking.slot.date >= date.today().isoformat():
            upcoming_bookings.append(booking)

    return render_template(
        "student_upcoming.html",
        bookings=upcoming_bookings
    )


@app.route("/student/history")
@role_required("Student")
def student_history():

    bookings = Booking.query.filter_by(
        student_id=session["user_id"]
    ).all()

    history_bookings = []

    for booking in bookings:
        if booking.status in ["Completed", "Cancelled"]:
            history_bookings.append(booking)

        elif booking.slot.date < date.today().isoformat():
            history_bookings.append(booking)

    return render_template(
        "student_history.html",
        bookings=history_bookings
    )


@app.route("/student/results")
@role_required("Student")
def student_results():

    evaluations = Evaluation.query.join(
        Booking,
        Evaluation.booking_id == Booking.id
    ).filter(
        Booking.student_id == session["user_id"],
        Evaluation.status == "Completed"
    ).all()

    return render_template(
        "student_results.html",
        evaluations=evaluations
    )


# -------------------------------------------------------------
# BULK STUDENT CSV IMPORT & SAMPLE CSV (Requirement 4)
# -------------------------------------------------------------
@app.route("/admin/students/import-csv", methods=["POST"])
@role_required("Admin")
def import_students_csv():
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Please select a valid CSV file to upload.", "danger")
        return redirect(url_for("admin_users"))

    if not file.filename.lower().endswith(".csv"):
        flash("Invalid file format. Please upload a .csv file.", "danger")
        return redirect(url_for("admin_users"))

    try:
        content = file.stream.read().decode("utf-8-sig")
        stream = io.StringIO(content, newline=None)
        reader = csv.DictReader(stream)

        if not reader.fieldnames:
            flash("The uploaded CSV file is empty.", "danger")
            return redirect(url_for("admin_users"))

        headers = [h.strip().lower() for h in reader.fieldnames if h]
        required = ["name", "email", "password", "roll_number"]
        if not all(r in headers for r in required):
            flash("CSV header missing required columns: name, email, password, roll_number.", "danger")
            return redirect(url_for("admin_users"))

        imported_count = 0
        skipped_count = 0

        for row in reader:
            clean = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
            name = clean.get("name")
            email = clean.get("email")
            password = clean.get("password")
            roll_number = clean.get("roll_number", "").upper()
            dept = clean.get("department") or "Data Science and Applications"
            year = clean.get("year") or "1st Year"
            phone = clean.get("phone") or ""

            if not name or not email or not password or not roll_number:
                skipped_count += 1
                continue

            # Check duplicate email or roll number
            existing_user = User.query.filter_by(email=email).first()
            existing_roll = StudentProfile.query.filter_by(roll_number=roll_number).first()
            if existing_user or existing_roll:
                skipped_count += 1
                continue

            hashed = generate_password_hash(password)
            user = User(name=name, email=email, password_hash=hashed, role="Student")
            user.is_approved = True
            user.is_active = True
            db.session.add(user)
            db.session.flush()

            profile = StudentProfile(
                user_id=user.id,
                roll_number=roll_number,
                department=dept,
                year=year,
                phone=phone
            )
            db.session.add(profile)
            imported_count += 1

        db.session.commit()
        flash(f"CSV Import Successful: {imported_count} student(s) added to college database. {skipped_count} row(s) skipped (duplicates or invalid).", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to parse CSV file: {str(e)}", "danger")

    return redirect(url_for("admin_users"))


@app.route("/admin/students/sample-csv")
@role_required("Admin")
def sample_students_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "email", "password", "roll_number", "department", "year", "phone"])
    writer.writerow(["Rahul Sharma", "rahul.sharma@college.edu", "student123", "23CS201", "Computer Science & Engineering", "3rd Year", "9812345678"])
    writer.writerow(["Neha Sen", "neha.sen@college.edu", "student123", "23DS202", "Data Science and Applications", "3rd Year", "9823456789"])
    writer.writerow(["Amit Roy", "amit.roy@college.edu", "student123", "24EE203", "Electrical Engineering", "2nd Year", "9834567890"])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=sample_students_template.csv"}
    )


# -------------------------------------------------------------
# COURSE & EXAM RESOURCES (Requirement 7)
# -------------------------------------------------------------
@app.route("/course/<int:course_id>/resources", methods=["GET", "POST"])
@role_required("Admin")
def course_resources(course_id):
    course = Course.query.get_or_404(course_id)

    if request.method == "POST":
        title = request.form.get("title")
        url = request.form.get("url")
        description = request.form.get("description")

        if not title or not title.strip() or not url or not url.strip():
            flash("Resource title and URL are required.", "danger")
            return redirect(url_for("course_resources", course_id=course.id))

        res = CourseResource(
            course_id=course.id,
            title=title.strip(),
            url=url.strip(),
            description=description.strip() if description else None
        )
        db.session.add(res)
        db.session.commit()
        flash("Study resource published successfully.", "success")
        return redirect(url_for("course_resources", course_id=course.id))

    return render_template("course_resources.html", course=course)


@app.route("/course/resource/<int:resource_id>/delete", methods=["POST"])
@role_required("Admin")
def delete_course_resource(resource_id):
    res = CourseResource.query.get_or_404(resource_id)
    cid = res.course_id
    db.session.delete(res)
    db.session.commit()
    flash("Resource deleted successfully.", "success")
    return redirect(url_for("course_resources", course_id=cid))


@app.route("/student/resources")
@role_required("Student")
def student_resources():
    courses = Course.query.all()
    return render_template("student_resources.html", courses=courses)


# -------------------------------------------------------------
# RESULT PDF & PRINTABLE REPORT (Requirement 10)
# -------------------------------------------------------------
@app.route("/student/result/<int:evaluation_id>/pdf")
@role_required("Student")
def download_result_pdf(evaluation_id):
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    if evaluation.booking.student_id != session["user_id"]:
        abort(403)

    pdf_bytes = generate_result_pdf(evaluation)
    student = evaluation.booking.student
    exam = evaluation.booking.slot.examination
    clean_exam = "".join(c for c in exam.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    filename = f"Result_Report_{student.roll_number or student.id}_{clean_exam}.pdf"

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@app.route("/student/result/<int:evaluation_id>/report")
def view_result_report(evaluation_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    evaluation = Evaluation.query.get_or_404(evaluation_id)
    role = session.get("user_role")

    if role == "Student" and evaluation.booking.student_id != session["user_id"]:
        abort(403)
    if role == "Examiner" and evaluation.examiner_id != session["user_id"]:
        abort(403)

    total_rubric_marks = sum(r.marks for r in evaluation.booking.slot.examination.rubrics) if evaluation.booking.slot.examination.rubrics else 100
    percentage = (evaluation.marks / total_rubric_marks * 100) if total_rubric_marks > 0 else 0

    return render_template(
        "result_report.html",
        evaluation=evaluation,
        total_rubric_marks=total_rubric_marks,
        percentage=percentage
    )


# -------------------------------------------------------------
# STUDENT CALENDAR (Requirement 3)
# -------------------------------------------------------------
@app.route("/student/calendar")
@role_required("Student")
def student_calendar():
    refresh_all_examinations()
    student_id = session["user_id"]
    bookings = Booking.query.filter_by(student_id=student_id).all()
    examinations = Examination.query.all()
    announcements = Announcement.query.filter(
        or_(Announcement.target_role == "All", Announcement.target_role == "Student")
    ).all()

    return render_template(
        "student_calendar.html",
        bookings=bookings,
        examinations=examinations,
        announcements=announcements
    )


# -------------------------------------------------------------
# EXAMINER TRACKING & ANALYTICS FOR ADMIN (Requirement 6)
# -------------------------------------------------------------
@app.route("/admin/examiners/analytics")
@role_required("Admin")
def admin_examiner_analytics():
    examiners = User.query.filter_by(role="Examiner", is_approved=True).all()
    examiner_data = []

    for ex in examiners:
        slots = ExaminationSlot.query.filter_by(examiner_id=ex.id).all()
        slot_ids = [s.id for s in slots]
        bookings = Booking.query.filter(Booking.slot_id.in_(slot_ids)).all() if slot_ids else []

        evaluations = Evaluation.query.filter_by(examiner_id=ex.id).all()
        completed_evals = [ev for ev in evaluations if ev.status == "Completed"]
        pending_evals = len(bookings) - len(completed_evals)
        if pending_evals < 0:
            pending_evals = 0

        marks_list = [ev.marks for ev in completed_evals if ev.marks is not None]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        highest_marks = max(marks_list) if marks_list else 0
        lowest_marks = min(marks_list) if marks_list else 0
        completion_pct = round((len(completed_evals) / len(bookings) * 100), 1) if bookings else (100 if completed_evals else 0)

        examiner_data.append({
            "examiner": ex,
            "slots_count": len(slots),
            "bookings_count": len(bookings),
            "completed_count": len(completed_evals),
            "pending_count": pending_evals,
            "avg_marks": avg_marks,
            "highest_marks": highest_marks,
            "lowest_marks": lowest_marks,
            "completion_pct": completion_pct
        })

    return render_template("admin_examiner_analytics.html", examiners_data=examiner_data)


# -------------------------------------------------------------
# EXAMINER HISTORY & EVALUATION ARCHIVE (Requirement 11)
# -------------------------------------------------------------
@app.route("/examiner/history")
@role_required("Examiner")
def examiner_history():
    examiner_id = session["user_id"]
    evaluations = Evaluation.query.filter_by(
        examiner_id=examiner_id,
        status="Completed"
    ).order_by(Evaluation.id.desc()).all()

    marks_list = [ev.marks for ev in evaluations if ev.marks is not None]
    avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
    highest_marks = max(marks_list) if marks_list else 0
    lowest_marks = min(marks_list) if marks_list else 0

    grade_dist = {"90-100%": 0, "75-89%": 0, "60-74%": 0, "<60%": 0}
    for ev in evaluations:
        total_m = sum(r.marks for r in ev.booking.slot.examination.rubrics) if ev.booking.slot.examination.rubrics else 100
        pct = (ev.marks / total_m * 100) if total_m > 0 else 0
        if pct >= 90:
            grade_dist["90-100%"] += 1
        elif pct >= 75:
            grade_dist["75-89%"] += 1
        elif pct >= 60:
            grade_dist["60-74%"] += 1
        else:
            grade_dist["<60%"] += 1

    return render_template(
        "examiner_history.html",
        evaluations=evaluations,
        total_completed=len(evaluations),
        avg_marks=avg_marks,
        highest_marks=highest_marks,
        lowest_marks=lowest_marks,
        grade_dist=grade_dist
    )


# -------------------------------------------------------------
# STUDENT PERFORMANCE ANALYTICS FOR EVERY ROLE (Requirement 8)
# -------------------------------------------------------------
@app.route("/analytics")
def performance_analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("user_role")
    user_id = session["user_id"]

    if role == "Student":
        bookings = Booking.query.filter_by(student_id=user_id).all()
        evaluations = Evaluation.query.join(Booking).filter(
            Booking.student_id == user_id,
            Evaluation.status == "Completed"
        ).order_by(Evaluation.id.asc()).all()

        attempts = len(bookings)
        marks_list = [ev.marks for ev in evaluations if ev.marks is not None]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        highest_marks = max(marks_list) if marks_list else 0

        trend_labels = [ev.booking.slot.examination.name for ev in evaluations]
        trend_scores = [ev.marks for ev in evaluations]

        return render_template(
            "performance_analytics.html",
            role=role,
            attempts=attempts,
            completed_count=len(evaluations),
            avg_marks=avg_marks,
            highest_marks=highest_marks,
            trend_labels=trend_labels,
            trend_scores=trend_scores,
            evaluations=evaluations
        )

    elif role == "Examiner":
        evaluations = Evaluation.query.filter_by(
            examiner_id=user_id,
            status="Completed"
        ).order_by(Evaluation.id.asc()).all()

        marks_list = [ev.marks for ev in evaluations if ev.marks is not None]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        highest_marks = max(marks_list) if marks_list else 0

        exam_names = list(set([ev.booking.slot.examination.name for ev in evaluations]))
        exam_avg_marks = []
        for name in exam_names:
            sub = [ev.marks for ev in evaluations if ev.booking.slot.examination.name == name]
            exam_avg_marks.append(round(sum(sub) / len(sub), 1) if sub else 0)

        return render_template(
            "performance_analytics.html",
            role=role,
            attempts=len(evaluations),
            completed_count=len(evaluations),
            avg_marks=avg_marks,
            highest_marks=highest_marks,
            trend_labels=exam_names,
            trend_scores=exam_avg_marks,
            evaluations=evaluations
        )

    elif role == "Admin":
        all_evals = Evaluation.query.filter_by(status="Completed").all()
        all_bookings = Booking.query.count()
        marks_list = [ev.marks for ev in all_evals if ev.marks is not None]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        highest_marks = max(marks_list) if marks_list else 0

        courses = Course.query.all()
        course_labels = []
        course_averages = []
        for c in courses:
            c_evals = [ev for ev in all_evals if ev.booking.slot.examination.course_id == c.id and ev.marks is not None]
            course_labels.append(c.name)
            if c_evals:
                course_averages.append(round(sum(ev.marks for ev in c_evals) / len(c_evals), 1))
            else:
                course_averages.append(0)

        return render_template(
            "performance_analytics.html",
            role=role,
            attempts=all_bookings,
            completed_count=len(all_evals),
            avg_marks=avg_marks,
            highest_marks=highest_marks,
            trend_labels=course_labels,
            trend_scores=course_averages,
            evaluations=all_evals
        )

    return redirect(url_for("index"))


# -------------------------------------------------------------
# ANNOUNCEMENT MANAGEMENT (Requirement 12)
# -------------------------------------------------------------
@app.route("/admin/announcements", methods=["GET", "POST"])
@role_required("Admin")
def admin_announcements():
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        target_role = request.form.get("target_role", "All")
        event_date = request.form.get("event_date")

        if not title or not title.strip() or not content or not content.strip():
            flash("Title and content are required.", "danger")
            return redirect(url_for("admin_announcements"))

        ann = Announcement(
            title=title.strip(),
            content=content.strip(),
            target_role=target_role,
            event_date=event_date or None
        )
        db.session.add(ann)
        db.session.commit()

        # Broadcast notification
        notify_all(
            title=f"Announcement: {ann.title}",
            message=ann.content[:150] + ("..." if len(ann.content) > 150 else ""),
            role=ann.target_role,
            category="announcement"
        )

        flash("Announcement published successfully and notified to users.", "success")
        return redirect(url_for("admin_announcements"))

    announcements = Announcement.query.order_by(Announcement.id.desc()).all()
    return render_template("admin_announcements.html", announcements=announcements)


@app.route("/admin/announcement/<int:announcement_id>/delete", methods=["POST"])
@role_required("Admin")
def delete_announcement(announcement_id):
    ann = Announcement.query.get_or_404(announcement_id)
    db.session.delete(ann)
    db.session.commit()
    flash("Announcement deleted successfully.", "success")
    return redirect(url_for("admin_announcements"))


# -------------------------------------------------------------
# NOTIFICATION CENTRE (Requirement 9)
# -------------------------------------------------------------
@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    user_notifications = Notification.query.filter_by(
        user_id=user_id
    ).order_by(Notification.id.desc()).all()
    return render_template("notifications.html", notifications=user_notifications)


@app.route("/notification/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    notif = Notification.query.filter_by(
        id=notification_id, user_id=session["user_id"]
    ).first_or_404()
    notif.is_read = True
    db.session.commit()
    return redirect(url_for("notifications"))


@app.route("/notifications/read-all", methods=["POST"])
def mark_all_notifications_read():
    if "user_id" not in session:
        return redirect(url_for("login"))
    Notification.query.filter_by(
        user_id=session["user_id"], is_read=False
    ).update({"is_read": True})
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications"))

if __name__ == "__main__":
    app.run(debug=True)