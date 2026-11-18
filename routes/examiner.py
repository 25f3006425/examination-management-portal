from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, abort
from sqlalchemy import or_
from database import db
from models import (
    User, Examination, ExaminationSlot, Booking,
    ExaminationRubric, Evaluation, ExaminerProfile, EvaluationMark, Announcement
)
from helpers import role_required, notify_user


@role_required("Examiner")
def examiner_dashboard():
    examiner_id = session["user_id"]
    slots = ExaminationSlot.query.filter_by(examiner_id=examiner_id).all()

    assigned_exams = {s.examination_id for s in slots}
    total_slots = len(slots)
    booking_count = sum(Booking.query.filter_by(slot_id=s.id, status="Booked").count() for s in slots)

    pending_evals = 0
    for s in slots:
        for b in Booking.query.filter_by(slot_id=s.id, status="Booked").all():
            ev = Evaluation.query.filter_by(booking_id=b.id).first()
            if not ev or ev.status == "Pending":
                pending_evals += 1

    announcements = Announcement.query.filter(
        or_(Announcement.target_role == "All", Announcement.target_role == "Examiner")
    ).order_by(Announcement.id.desc()).limit(3).all()

    examiner = db.session.get(User, examiner_id) if hasattr(db.session, "get") else User.query.get(examiner_id)

    return render_template(
        "examiner_dashboard.html",
        examiner=examiner,
        total_examinations=len(assigned_exams),
        total_slots=total_slots,
        total_bookings=booking_count,
        pending_evaluations=pending_evals,
        announcements=announcements
    )


@role_required("Examiner")
def evaluate_student(booking_id):
    examiner_id = session["user_id"]
    booking = Booking.query.get_or_404(booking_id)

    if booking.status != "Booked":
        flash("Evaluation not allowed for this booking.")
        return redirect(url_for("examiner_bookings"))

    if booking.slot.examiner_id != examiner_id:
        abort(403)

    rubrics = ExaminationRubric.query.filter_by(examination_id=booking.slot.examination_id).all()
    if not rubrics:
        flash("This exam has no rubrics defined yet.")
        return redirect(url_for("examiner_bookings"))

    evaluation = Evaluation.query.filter_by(booking_id=booking.id).first()

    if request.method == "POST":
        total_marks = 0
        marks_list = []

        for rubric in rubrics:
            marks = request.form.get(f"rubric_{rubric.id}", type=int)
            if marks is None or marks < 0 or marks > rubric.marks:
                flash("Please award valid marks for each rubric.")
                return redirect(url_for("evaluate_student", booking_id=booking.id))
            total_marks += marks
            marks_list.append((rubric, marks))

        remarks = request.form.get("remarks")
        if not evaluation:
            evaluation = Evaluation(booking_id=booking.id, examiner_id=examiner_id)
            db.session.add(evaluation)
            db.session.flush()

        evaluation.marks = total_marks
        evaluation.remarks = remarks
        evaluation.status = "Completed"
        booking.status = "Completed"

        for rubric, marks in marks_list:
            mark_entry = EvaluationMark.query.filter_by(evaluation_id=evaluation.id, rubric_id=rubric.id).first()
            if not mark_entry:
                db.session.add(EvaluationMark(evaluation_id=evaluation.id, rubric_id=rubric.id, marks=marks))
            else:
                mark_entry.marks = marks

        db.session.commit()

        notify_user(
            booking.student_id,
            "Examination Result Published",
            f"Your evaluation for {booking.slot.examination.name} is complete. Total Marks: {total_marks}.",
            "result"
        )
        flash("Evaluation saved.")
        return redirect(url_for("examiner_bookings"))

    marks_by_rubric = {}
    if evaluation:
        for sm in EvaluationMark.query.filter_by(evaluation_id=evaluation.id).all():
            marks_by_rubric[sm.rubric_id] = sm.marks

    return render_template(
        "evaluate_student.html",
        booking=booking,
        rubrics=rubrics,
        evaluation=evaluation,
        marks_by_rubric=marks_by_rubric
    )


@role_required("Examiner")
def examiner_bookings():
    examiner_id = session["user_id"]
    slots = ExaminationSlot.query.filter_by(examiner_id=examiner_id).all()
    bookings = []
    for s in slots:
        bookings.extend(Booking.query.filter_by(slot_id=s.id, status="Booked").all())

    return render_template("examiner_bookings.html", bookings=bookings)


@role_required("Examiner")
def examiner_slots():
    examiner_id = session["user_id"]
    if request.method == "POST":
        exam_id = request.form.get("examination_id", type=int)
        slot_date = request.form.get("date")
        time = request.form.get("time")

        exam = Examination.query.get(exam_id)
        if not exam or not exam.slot_creation_open:
            flash("Slot creation window is closed.")
            return redirect(url_for("examiner_slots"))

        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        if not exam.slot_creation_start or not exam.slot_creation_end or now < exam.slot_creation_start or now > exam.slot_creation_end:
            flash("Current time is outside the slot creation window.")
            return redirect(url_for("examiner_slots"))

        if not slot_date or not time or f"{slot_date}T{time}" < now:
            flash("Slot date and time must be in the future.")
            return redirect(url_for("examiner_slots"))

        db.session.add(ExaminationSlot(examination_id=exam_id, examiner_id=examiner_id, date=slot_date, time=time))
        db.session.commit()
        flash("New slot added to your schedule.")
        return redirect(url_for("examiner_slots"))

    exams = Examination.query.filter_by(slot_creation_open=True).all()
    slots = ExaminationSlot.query.filter_by(examiner_id=examiner_id).all()
    return render_template("examiner_slots.html", examinations=exams, slots=slots)


@role_required("Examiner")
def edit_examiner_slot(slot_id):
    examiner_id = session["user_id"]
    slot = ExaminationSlot.query.get_or_404(slot_id)

    if slot.examiner_id != examiner_id:
        abort(403)

    if slot.examination.booking_open or Booking.query.filter_by(slot_id=slot.id).count() > 0:
        flash("Cannot edit a slot that is already open or booked.")
        return redirect(url_for("examiner_slots"))

    if request.method == "POST":
        slot_date = request.form.get("date")
        time = request.form.get("time")
        now = datetime.now().strftime("%Y-%m-%dT%H:%M")

        if not slot_date or not time or f"{slot_date}T{time}" < now:
            flash("Slot date and time must be in the future.")
            return redirect(url_for("edit_examiner_slot", slot_id=slot.id))

        slot.date = slot_date
        slot.time = time
        db.session.commit()
        flash("Slot timing updated.")
        return redirect(url_for("examiner_slots"))

    return render_template("edit_examiner_slot.html", slot=slot)


@role_required("Examiner")
def delete_examiner_slot(slot_id):
    examiner_id = session["user_id"]
    slot = ExaminationSlot.query.get_or_404(slot_id)

    if slot.examiner_id != examiner_id:
        abort(403)

    if slot.examination.booking_open or Booking.query.filter_by(slot_id=slot.id).count() > 0:
        flash("Cannot remove a slot with enrolled students.")
        return redirect(url_for("examiner_slots"))

    db.session.delete(slot)
    db.session.commit()
    flash("Slot removed from schedule.")
    return redirect(url_for("examiner_slots"))


@role_required("Examiner")
def examiner_profile():
    examiner_id = session["user_id"]
    examiner = User.query.get_or_404(examiner_id)
    profile = ExaminerProfile.query.filter_by(user_id=examiner_id).first()

    if not profile:
        profile = ExaminerProfile(user_id=examiner_id)
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        examiner.name = request.form.get("name")
        profile.qualification = request.form.get("qualification")
        profile.specialization = request.form.get("specialization")
        db.session.commit()
        flash("Examiner profile saved.")
        return redirect(url_for("examiner_profile"))

    return render_template("examiner_profile.html", examiner=examiner, profile=profile)


@role_required("Examiner")
def examiner_examinations():
    examiner_id = session["user_id"]
    exams = Examination.query.join(ExaminationSlot).filter(ExaminationSlot.examiner_id == examiner_id).distinct().all()
    return render_template("examiner_examinations.html", examinations=exams)


@role_required("Examiner")
def examiner_history():
    examiner_id = session["user_id"]
    evals = Evaluation.query.filter_by(examiner_id=examiner_id, status="Completed").order_by(Evaluation.id.desc()).all()

    marks_list = [ev.marks for ev in evals if ev.marks is not None]
    avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
    highest_marks = max(marks_list) if marks_list else 0
    lowest_marks = min(marks_list) if marks_list else 0

    grade_dist = {"90-100%": 0, "75-89%": 0, "60-74%": 0, "<60%": 0}
    for ev in evals:
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
        evaluations=evals,
        total_completed=len(evals),
        avg_marks=avg_marks,
        highest_marks=highest_marks,
        lowest_marks=lowest_marks,
        grade_dist=grade_dist
    )


def register_routes(app):
    app.add_url_rule("/examiner_dashboard", "examiner_dashboard", examiner_dashboard)
    app.add_url_rule("/examiner/evaluate/<int:booking_id>", "evaluate_student", evaluate_student, methods=["GET", "POST"])
    app.add_url_rule("/examiner/bookings", "examiner_bookings", examiner_bookings)
    app.add_url_rule("/examiner/slots", "examiner_slots", examiner_slots, methods=["GET", "POST"])
    app.add_url_rule("/examiner/slots/edit/<int:slot_id>", "edit_examiner_slot", edit_examiner_slot, methods=["GET", "POST"])
    app.add_url_rule("/examiner/slots/delete/<int:slot_id>", "delete_examiner_slot", delete_examiner_slot, methods=["POST"])
    app.add_url_rule("/examiner/profile", "examiner_profile", examiner_profile, methods=["GET", "POST"])
    app.add_url_rule("/examiner/examinations", "examiner_examinations", examiner_examinations)
    app.add_url_rule("/examiner/history", "examiner_history", examiner_history)
