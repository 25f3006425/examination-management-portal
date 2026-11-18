from datetime import date
from flask import render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash
from sqlalchemy import or_
from database import db
from models import (
    User, Course, Examination, ExaminationSlot, Booking,
    Evaluation, StudentProfile, Announcement
)
from helpers import role_required, refresh_all_examinations, notify_user


@role_required("Student")
def student_dashboard():
    refresh_all_examinations()
    student_id = session["user_id"]
    student = User.query.get_or_404(student_id)

    all_bookings = Booking.query.filter_by(student_id=student_id).all()
    booking_count = len(all_bookings)

    today = date.today().isoformat()
    upcoming_bookings = [b for b in all_bookings if b.status == "Booked" and b.slot.date >= today]
    upcoming_exams = len(upcoming_bookings)
    completed_exams = len([b for b in all_bookings if b.status == "Completed"])

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

    return render_template(
        "student_dashboard.html",
        student=student,
        total_bookings=booking_count,
        upcoming_examinations=upcoming_exams,
        completed_examinations=completed_exams,
        upcoming_bookings=upcoming_bookings,
        all_results=evaluations,
        current_results=current_results,
        previous_results=previous_results,
        avg_marks=avg_marks,
        highest_marks=highest_marks,
        announcements=announcements,
        courses=Course.query.all()
    )


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
        name = (request.form.get("name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        dept = (request.form.get("department") or "").strip()
        year = (request.form.get("year") or "").strip()
        new_pwd = (request.form.get("new_password") or "").strip()

        if not name:
            flash("Name cannot be empty.", "danger")
            return redirect(url_for("student_profile"))

        student.name = name
        session["user_name"] = student.name
        profile.phone = phone
        if dept:
            profile.department = dept
        if year:
            profile.year = year
        if new_pwd:
            student.password_hash = generate_password_hash(new_pwd)

        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("student_profile"))

    return render_template("student_profile.html", student=student, profile=profile)


@role_required("Student")
def student_examinations():
    search = (request.args.get("search") or "").strip()
    query = Examination.query.filter_by(booking_open=True)

    if search:
        if search.isdigit():
            query = query.filter(or_(Examination.name.ilike(f"%{search}%"), Examination.id == int(search)))
        else:
            query = query.filter(Examination.name.ilike(f"%{search}%"))

    return render_template("student_examinations.html", examinations=query.all(), search=search)


@role_required("Student")
def student_examination_slots(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    today = date.today().isoformat()
    slots = ExaminationSlot.query.filter_by(examination_id=examination_id).filter(ExaminationSlot.date >= today).all()

    available_slots = []
    for slot in slots:
        booked = Booking.query.filter_by(slot_id=slot.id, status="Booked").count()
        remaining = slot.capacity - booked
        if remaining > 0:
            available_slots.append({"slot": slot, "remaining_seats": remaining})

    return render_template("student_slots.html", examination=exam, available_slots=available_slots)


@role_required("Student")
def student_book_slot(slot_id):
    student_id = session["user_id"]
    slot = ExaminationSlot.query.get_or_404(slot_id)
    exam = slot.examination
    today = date.today().isoformat()

    if not exam.booking_open or slot.date < today:
        flash("Booking closed or slot has passed.", "danger")
        return redirect(url_for("student_examination_slots", examination_id=exam.id))

    existing = Booking.query.join(ExaminationSlot).filter(
        Booking.student_id == student_id,
        Booking.status == "Booked",
        ExaminationSlot.examination_id == exam.id
    ).first()

    if existing:
        flash("You already have an active booking for this exam.", "warning")
        return redirect(url_for("student_examination_slots", examination_id=exam.id))

    booked_count = Booking.query.filter_by(slot_id=slot.id, status="Booked").count()
    if booked_count >= slot.capacity:
        flash("This slot has no remaining capacity.", "danger")
        return redirect(url_for("student_examination_slots", examination_id=exam.id))

    booking = Booking(student_id=student_id, slot_id=slot.id, status="Booked")
    db.session.add(booking)
    db.session.commit()

    notify_user(
        student_id,
        "Booking Confirmed",
        f"Your examination slot for {exam.name} on {slot.date} at {slot.time} has been booked.",
        "booking"
    )
    flash("Slot booked!", "success")
    return redirect(url_for("student_bookings"))


@role_required("Student")
def student_bookings():
    bookings = Booking.query.filter_by(student_id=session["user_id"], status="Booked").all()
    return render_template("student_bookings.html", bookings=bookings)


@role_required("Student")
def student_cancel_booking(booking_id):
    booking = Booking.query.filter_by(id=booking_id, student_id=session["user_id"]).first_or_404()

    if booking.status != "Booked":
        flash("This booking is no longer cancellable.", "danger")
        return redirect(url_for("student_bookings"))

    exam = booking.slot.examination
    if exam.booking_end and date.today().isoformat() > exam.booking_end:
        flash("Cancellation cutoff date has passed.", "danger")
        return redirect(url_for("student_bookings"))

    booking.status = "Cancelled"
    db.session.commit()

    notify_user(
        session["user_id"],
        "Booking Cancelled",
        f"Your booking for {exam.name} on {booking.slot.date} has been cancelled.",
        "cancellation"
    )
    flash("Booking cancelled.", "success")
    return redirect(url_for("student_bookings"))


@role_required("Student")
def student_upcoming():
    today = date.today().isoformat()
    bookings = Booking.query.filter_by(student_id=session["user_id"], status="Booked").all()
    upcoming = [b for b in bookings if b.slot.date >= today]
    return render_template("student_upcoming.html", bookings=upcoming)


@role_required("Student")
def student_history():
    today = date.today().isoformat()
    bookings = Booking.query.filter_by(student_id=session["user_id"]).all()
    history = [b for b in bookings if b.status in ["Completed", "Cancelled"] or b.slot.date < today]
    return render_template("student_history.html", bookings=history)


@role_required("Student")
def student_results():
    evals = Evaluation.query.join(Booking).filter(
        Booking.student_id == session["user_id"],
        Evaluation.status == "Completed"
    ).all()
    return render_template("student_results.html", evaluations=evals)


@role_required("Student")
def student_resources():
    return render_template("student_resources.html", courses=Course.query.all())


def view_result_report(evaluation_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    evaluation = Evaluation.query.get_or_404(evaluation_id)
    role = session.get("user_role")

    if (role == "Student" and evaluation.booking.student_id != session["user_id"]) or (role == "Examiner" and evaluation.examiner_id != session["user_id"]):
        abort(403)

    total_rubric_marks = sum(r.marks for r in evaluation.booking.slot.examination.rubrics) if evaluation.booking.slot.examination.rubrics else 100
    percentage = (evaluation.marks / total_rubric_marks * 100) if total_rubric_marks > 0 else 0

    return render_template(
        "result_report.html",
        evaluation=evaluation,
        total_rubric_marks=total_rubric_marks,
        percentage=percentage
    )


@role_required("Student")
def student_calendar():
    refresh_all_examinations()
    student_id = session["user_id"]
    bookings = Booking.query.filter_by(student_id=student_id).all()
    exams = Examination.query.all()
    announcements = Announcement.query.filter(
        or_(Announcement.target_role == "All", Announcement.target_role == "Student")
    ).all()

    return render_template(
        "student_calendar.html",
        bookings=bookings,
        examinations=exams,
        announcements=announcements
    )


def register_routes(app):
    app.add_url_rule("/student_dashboard", "student_dashboard", student_dashboard)
    app.add_url_rule("/student/profile", "student_profile", student_profile, methods=["GET", "POST"])
    app.add_url_rule("/student/examinations", "student_examinations", student_examinations)
    app.add_url_rule("/student/examinations/<int:examination_id>", "student_examination_slots", student_examination_slots)
    app.add_url_rule("/student/book-slot/<int:slot_id>", "student_book_slot", student_book_slot, methods=["POST"])
    app.add_url_rule("/student/bookings", "student_bookings", student_bookings)
    app.add_url_rule("/student/cancel-booking/<int:booking_id>", "student_cancel_booking", student_cancel_booking, methods=["POST"])
    app.add_url_rule("/student/upcoming", "student_upcoming", student_upcoming)
    app.add_url_rule("/student/history", "student_history", student_history)
    app.add_url_rule("/student/results", "student_results", student_results)
    app.add_url_rule("/student/resources", "student_resources", student_resources)
    app.add_url_rule("/student/result/<int:evaluation_id>/report", "view_result_report", view_result_report)
    app.add_url_rule("/student/calendar", "student_calendar", student_calendar)
