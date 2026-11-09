from sqlalchemy.sql.functions import user
from flask import Flask, render_template, request, redirect, url_for, flash, session
from database import db
from models import User
from functools import wraps
from flask import abort
from flask import render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import models
from models import User, Course, Examination, ExaminationSlot, Booking, ExaminationRubric


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///examination.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "zxcvbnmlkjhgfdsaqwertyuiop"

db.init_app(app)

with app.app_context():
    db.create_all()

from functools import wraps
from flask import abort

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
            if not user.is_active:
                session.clear()
                return redirect(url_for("login"))

            if user is None:
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

        # Find user using email
        user = User.query.filter_by(email=email).first()

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
    return render_template("examiner_dashboard.html")


# Student Dashboard
@app.route("/student_dashboard")
@role_required("Student")
def student_dashboard():
    return render_template("student_dashboard.html")

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

        examination.slot_creation_start = slot_start or None
        examination.slot_creation_end = slot_end or None
        examination.booking_start = booking_start or None
        examination.booking_end = booking_end or None

        db.session.commit()

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

    # Do not open slot creation without configured dates
    if not examination.slot_creation_open:
        if not examination.slot_creation_start or not examination.slot_creation_end:
            flash("Configure slot creation dates before opening it.")
            return redirect(url_for(
                "examination_settings",
                examination_id=examination.id
            ))

    examination.slot_creation_open = not examination.slot_creation_open

    db.session.commit()

    flash("Slot creation setting updated.")

    return redirect(url_for(
        "examination_settings",
        examination_id=examination.id
    ))

@app.route("/examination/<int:examination_id>/toggle-booking", methods=["POST"])
@role_required("Admin")
def toggle_booking(examination_id):

    examination = Examination.query.get_or_404(examination_id)

    # Do not open booking without configured dates
    if not examination.booking_open:
        if not examination.booking_start or not examination.booking_end:
            flash("Configure booking dates before opening booking.")
            return redirect(url_for(
                "examination_settings",
                examination_id=examination.id
            ))

    examination.booking_open = not examination.booking_open

    db.session.commit()

    flash("Booking setting updated.")

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

        # Prevent duplicate bookings by the same student
        existing_booking = Booking.query.filter_by(
            student_id=booking.student_id,
            slot_id=new_slot.id
        ).first()

        if existing_booking:
            flash("This student already has a booking in that slot.")
            return redirect(
                url_for("reschedule_booking", booking_id=booking.id)
            )

        booking.slot_id = new_slot.id

        db.session.commit()

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

if __name__ == "__main__":
    app.run(debug=True)