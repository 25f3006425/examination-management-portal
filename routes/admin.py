from flask import render_template, request, redirect, url_for, flash
from database import db
from models import (
    User, Course, Examination, ExaminationSlot, Booking,
    ExaminationRubric, Evaluation, CourseResource, Announcement
)
from helpers import role_required, update_examination_status, notify_user, notify_all


@role_required("Admin")
def admin_dashboard():
    total_courses = Course.query.count()
    total_examinations = Examination.query.count()
    total_examiners = User.query.filter_by(role="Examiner").count()
    total_students = User.query.filter_by(role="Student").count()
    total_slots = ExaminationSlot.query.count()
    booking_count = Booking.query.count()

    pending_examiners = User.query.filter_by(role="Examiner", is_approved=False).all()
    approved_examiners = User.query.filter_by(role="Examiner", is_approved=True, is_active=True).all()
    inactive_examiners = User.query.filter_by(role="Examiner", is_active=False).all()

    return render_template(
        "admin_dashboard.html",
        total_courses=total_courses,
        total_examinations=total_examinations,
        total_examiners=total_examiners,
        total_students=total_students,
        total_slots=total_slots,
        total_bookings=booking_count,
        pending_examiners=pending_examiners,
        approved_examiners=approved_examiners,
        inactive_examiners=inactive_examiners
    )


@role_required("Admin")
def approve_examiner(user_id):
    examiner = User.query.filter_by(id=user_id, role="Examiner").first_or_404()
    examiner.is_approved = True
    db.session.commit()
    flash("Examiner credentials approved.")
    return redirect(url_for("admin_dashboard"))


@role_required("Admin")
def deactivate_examiner(user_id):
    examiner = User.query.filter_by(id=user_id, role="Examiner").first_or_404()
    examiner.is_active = False
    db.session.commit()
    flash("Examiner account suspended.")
    return redirect(url_for("admin_dashboard"))


@role_required("Admin")
def reactivate_examiner(user_id):
    examiner = User.query.filter_by(id=user_id, role="Examiner").first_or_404()
    examiner.is_active = True
    db.session.commit()
    flash("Examiner account restored.")
    return redirect(url_for("admin_dashboard"))


@role_required("Admin")
def courses():
    return render_template("courses.html", courses=Course.query.all())


@role_required("Admin")
def add_course():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = request.form.get("description")

        if not name:
            flash("Course title cannot be empty.")
            return redirect(url_for("add_course"))

        course = Course(name=name, description=description)
        db.session.add(course)
        db.session.commit()

        res_title = (request.form.get("resource_title") or "").strip()
        res_url = (request.form.get("resource_url") or "").strip()
        if res_title and res_url:
            db.session.add(CourseResource(course_id=course.id, title=res_title, url=res_url))
            db.session.commit()

        flash("New course created.")
        return redirect(url_for("courses"))

    return render_template("add_course.html")


@role_required("Admin")
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Course title cannot be empty.")
            return redirect(url_for("edit_course", course_id=course.id))

        course.name = name
        course.description = request.form.get("description")
        db.session.commit()
        flash("Course details updated.")
        return redirect(url_for("courses"))

    return render_template("edit_course.html", course=course)


@role_required("Admin")
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.examinations:
        flash("Cannot remove a course that has scheduled exams.")
        return redirect(url_for("courses"))

    db.session.delete(course)
    db.session.commit()
    flash("Course removed.")
    return redirect(url_for("courses"))


@role_required("Admin")
def examinations():
    search = (request.args.get("search") or "").strip().lower()
    exams = Examination.query.all()
    for exam in exams:
        update_examination_status(exam)

    if search:
        exams = [
            ex for ex in exams
            if search in str(ex.id) or search in ex.name.lower() or search in ex.course.name.lower()
        ]

    return render_template("examinations.html", examinations=exams, search=search)


@role_required("Admin")
def add_examination():
    all_courses = Course.query.all()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        course_id = request.form.get("course_id", type=int)

        if not name or not course_id or not Course.query.get(course_id):
            flash("Please provide an exam name and select a course.")
            return redirect(url_for("add_examination"))

        db.session.add(Examination(name=name, course_id=course_id))
        db.session.commit()
        flash("Exam added to catalog.")
        return redirect(url_for("examinations"))

    return render_template("add_examination.html", courses=all_courses)


@role_required("Admin")
def edit_examination(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    all_courses = Course.query.all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        course_id = request.form.get("course_id", type=int)

        if not name or not course_id or not Course.query.get(course_id):
            flash("Please provide an exam name and select a course.")
            return redirect(url_for("edit_examination", examination_id=exam.id))

        exam.name = name
        exam.course_id = course_id
        db.session.commit()
        flash("Exam details saved.")
        return redirect(url_for("examinations"))

    return render_template("edit_examination.html", examination=exam, courses=all_courses)


@role_required("Admin")
def delete_examination(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    if exam.slots or exam.rubrics:
        flash("Cannot remove an exam with existing slots or rubrics.")
        return redirect(url_for("examinations"))

    db.session.delete(exam)
    db.session.commit()
    flash("Exam removed.")
    return redirect(url_for("examinations"))


@role_required("Admin")
def manage_rubrics(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    rubrics = ExaminationRubric.query.filter_by(examination_id=examination_id).all()
    total_marks = sum(r.marks for r in rubrics)
    return render_template("rubrics.html", examination=exam, rubrics=rubrics, total_marks=total_marks)


@role_required("Admin")
def add_rubric(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    if request.method == "POST":
        criterion = (request.form.get("criterion") or "").strip()
        marks = request.form.get("marks", type=int)

        if not criterion or not marks or marks <= 0:
            flash("Please enter a rubric criterion and valid marks.")
            return redirect(url_for("add_rubric", examination_id=examination_id))

        rubric = ExaminationRubric(examination_id=examination_id, criterion=criterion, marks=marks)
        db.session.add(rubric)
        db.session.commit()
        flash("Rubric criterion added.")
        return redirect(url_for("manage_rubrics", examination_id=examination_id))

    return render_template("add_rubric.html", examination=exam)


@role_required("Admin")
def edit_rubric(rubric_id):
    rubric = ExaminationRubric.query.get_or_404(rubric_id)
    if request.method == "POST":
        criterion = (request.form.get("criterion") or "").strip()
        marks = request.form.get("marks", type=int)

        if not criterion or not marks or marks <= 0:
            flash("Please enter a rubric criterion and valid marks.")
            return redirect(url_for("edit_rubric", rubric_id=rubric.id))

        rubric.criterion = criterion
        rubric.marks = marks
        db.session.commit()
        flash("Rubric criterion updated.")
        return redirect(url_for("manage_rubrics", examination_id=rubric.examination_id))

    return render_template("edit_rubric.html", rubric=rubric)


@role_required("Admin")
def delete_rubric(rubric_id):
    rubric = ExaminationRubric.query.get_or_404(rubric_id)
    eid = rubric.examination_id
    db.session.delete(rubric)
    db.session.commit()
    flash("Rubric removed.")
    return redirect(url_for("manage_rubrics", examination_id=eid))


@role_required("Admin")
def examination_settings(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    if request.method == "POST":
        slot_start = request.form.get("slot_creation_start")
        slot_end = request.form.get("slot_creation_end")
        booking_start = request.form.get("booking_start")
        booking_end = request.form.get("booking_end")

        if bool(slot_start) != bool(slot_end) or (slot_start and slot_start > slot_end):
            flash("Slot creation end must follow start time.")
            return redirect(url_for("examination_settings", examination_id=exam.id))

        if bool(booking_start) != bool(booking_end) or (booking_start and booking_start > booking_end):
            flash("Booking deadline must follow booking start.")
            return redirect(url_for("examination_settings", examination_id=exam.id))

        if slot_end and booking_start and booking_start < slot_end:
            flash(f"Constraint Violation: Booking dates must be after slot creation ends (Slot creation end: {slot_end.replace('T', ' ')}).", "danger")
            return redirect(url_for("examination_settings", examination_id=exam.id))

        exam.slot_creation_start = slot_start or None
        exam.slot_creation_end = slot_end or None
        exam.booking_start = booking_start or None
        exam.booking_end = booking_end or None

        update_examination_status(exam)
        flash("Examination timelines saved successfully.")
        return redirect(url_for("examination_settings", examination_id=exam.id))

    return render_template("examination_settings.html", examination=exam)


@role_required("Admin")
def toggle_slot_creation(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    if exam.slot_creation_open:
        exam.slot_creation_override = "closed"
        exam.slot_creation_open = False
        flash("Faculty slot creation paused.", "warning")
    else:
        exam.slot_creation_override = "open"
        exam.slot_creation_open = True
        flash("Faculty slot creation opened.", "success")

    update_examination_status(exam)
    return redirect(url_for("examination_settings", examination_id=exam.id))


@role_required("Admin")
def reset_slot_override(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    exam.slot_creation_override = None
    update_examination_status(exam)
    flash("Slot creation restored to timeline schedule.", "info")
    return redirect(url_for("examination_settings", examination_id=exam.id))


@role_required("Admin")
def toggle_booking(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    if exam.booking_open:
        exam.booking_override = "closed"
        exam.booking_open = False
        flash("Student booking paused.", "warning")
    else:
        exam.booking_override = "open"
        exam.booking_open = True
        flash("Student booking opened.", "success")

    update_examination_status(exam)
    return redirect(url_for("examination_settings", examination_id=exam.id))


@role_required("Admin")
def reset_booking_override(examination_id):
    exam = Examination.query.get_or_404(examination_id)
    exam.booking_override = None
    update_examination_status(exam)
    flash("Booking restored to timeline schedule.", "info")
    return redirect(url_for("examination_settings", examination_id=exam.id))


@role_required("Admin")
def admin_slots():
    search = (request.args.get("search") or "").strip()
    slots = ExaminationSlot.query.all()
    if search:
        s = search.lower()
        slots = [
            slot for slot in slots
            if s in str(slot.id).lower() or s in slot.examination.name.lower() or s in slot.examiner.name.lower()
        ]

    examiners = User.query.filter_by(role="Examiner", is_approved=True, is_active=True).all()
    return render_template("admin_slots.html", slots=slots, examiners=examiners, search=search)


@role_required("Admin")
def change_slot_examiner(slot_id):
    slot = ExaminationSlot.query.get_or_404(slot_id)
    examiner_id = request.form.get("examiner_id", type=int)
    examiner = User.query.filter_by(id=examiner_id, role="Examiner", is_approved=True, is_active=True).first()

    if not examiner:
        flash("Please choose an approved, active examiner.")
        return redirect(url_for("admin_slots"))

    slot.examiner_id = examiner.id
    db.session.commit()
    flash("Examiner assigned to slot.")
    return redirect(url_for("admin_slots"))


@role_required("Admin")
def admin_bookings():
    search = (request.args.get("search") or "").strip().lower()
    bookings = Booking.query.all()
    if search:
        bookings = [
            b for b in bookings
            if search in str(b.id) or search in b.student.name.lower() or search in b.student.email.lower() or search in b.slot.examination.name.lower()
        ]
    return render_template("admin_bookings.html", bookings=bookings, search=search)


@role_required("Admin")
def reschedule_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    available_slots = ExaminationSlot.query.filter_by(examination_id=booking.slot.examination_id).all()

    if request.method == "POST":
        new_slot_id = request.form.get("slot_id", type=int)
        new_slot = ExaminationSlot.query.filter_by(id=new_slot_id, examination_id=booking.slot.examination_id).first()

        if not new_slot or new_slot.id == booking.slot_id:
            flash("Please pick a different available slot.")
            return redirect(url_for("reschedule_booking", booking_id=booking.id))

        if booking.status != "Booked":
            flash("Only active reservations can be moved.")
            return redirect(url_for("admin_bookings"))

        booked_count = Booking.query.filter_by(slot_id=new_slot.id, status="Booked").count()
        if booked_count >= new_slot.capacity:
            flash("That slot has reached maximum capacity.")
            return redirect(url_for("reschedule_booking", booking_id=booking.id))

        booking.slot_id = new_slot.id
        db.session.commit()

        notify_user(
            booking.student_id,
            "Booking Rescheduled",
            f"Your booking for {booking.slot.examination.name} was moved to {new_slot.date} at {new_slot.time}.",
            "reschedule"
        )
        flash("Session rescheduled.")
        return redirect(url_for("admin_bookings"))

    return render_template("reschedule_booking.html", booking=booking, slots=available_slots)


@role_required("Admin")
def admin_users():
    search = (request.args.get("search") or "").strip().lower()
    students = User.query.filter_by(role="Student").all()
    examiners = User.query.filter_by(role="Examiner").all()

    if search:
        students = [s for s in students if search in str(s.id) or search in s.name.lower() or search in s.email.lower()]
        examiners = [e for e in examiners if search in str(e.id) or search in e.name.lower() or search in e.email.lower()]

    return render_template("admin_users.html", students=students, examiners=examiners, search=search)




@role_required("Admin")
def course_resources(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        url = (request.form.get("url") or "").strip()
        desc = (request.form.get("description") or "").strip()

        if not title or not url:
            flash("Resource title and URL cannot be blank.", "danger")
            return redirect(url_for("course_resources", course_id=course.id))

        db.session.add(CourseResource(course_id=course.id, title=title, url=url, description=desc or None))
        db.session.commit()
        flash("Study resource published successfully.", "success")
        return redirect(url_for("course_resources", course_id=course.id))

    return render_template("course_resources.html", course=course)


@role_required("Admin")
def delete_course_resource(resource_id):
    res = CourseResource.query.get_or_404(resource_id)
    cid = res.course_id
    db.session.delete(res)
    db.session.commit()
    flash("Study material deleted.")
    return redirect(url_for("course_resources", course_id=cid))


@role_required("Admin")
def admin_examiner_analytics():
    examiners = User.query.filter_by(role="Examiner", is_approved=True).all()
    examiner_data = []

    for ex in examiners:
        slots = ExaminationSlot.query.filter_by(examiner_id=ex.id).all()
        slot_ids = [s.id for s in slots]
        bookings = Booking.query.filter(Booking.slot_id.in_(slot_ids)).all() if slot_ids else []

        evals = Evaluation.query.filter_by(examiner_id=ex.id).all()
        completed = [ev for ev in evals if ev.status == "Completed"]
        pending = max(0, len(bookings) - len(completed))

        marks_list = [ev.marks for ev in completed if ev.marks is not None]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        highest_marks = max(marks_list) if marks_list else 0
        lowest_marks = min(marks_list) if marks_list else 0
        completion_pct = round((len(completed) / len(bookings) * 100), 1) if bookings else (100 if completed else 0)

        examiner_data.append({
            "examiner": ex,
            "slots_count": len(slots),
            "bookings_count": len(bookings),
            "completed_count": len(completed),
            "pending_count": pending,
            "avg_marks": avg_marks,
            "highest_marks": highest_marks,
            "lowest_marks": lowest_marks,
            "completion_pct": completion_pct
        })

    return render_template("admin_examiner_analytics.html", examiners_data=examiner_data)


@role_required("Admin")
def admin_announcements():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        content = (request.form.get("content") or "").strip()
        target_role = request.form.get("target_role", "All")
        event_date = request.form.get("event_date")

        if not title or not content:
            flash("Announcement title and message body required.", "danger")
            return redirect(url_for("admin_announcements"))

        ann = Announcement(
            title=title,
            content=content,
            target_role=target_role,
            event_date=event_date or None
        )
        db.session.add(ann)
        db.session.commit()

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


@role_required("Admin")
def delete_announcement(announcement_id):
    ann = Announcement.query.get_or_404(announcement_id)
    db.session.delete(ann)
    db.session.commit()
    flash("Announcement deleted.")
    return redirect(url_for("admin_announcements"))


def register_routes(app):
    app.add_url_rule("/admin_dashboard", "admin_dashboard", admin_dashboard)
    app.add_url_rule("/approve_examiner/<int:user_id>", "approve_examiner", approve_examiner, methods=["POST"])
    app.add_url_rule("/deactivate_examiner/<int:user_id>", "deactivate_examiner", deactivate_examiner, methods=["POST"])
    app.add_url_rule("/reactivate_examiner/<int:user_id>", "reactivate_examiner", reactivate_examiner, methods=["POST"])
    app.add_url_rule("/courses", "courses", courses)
    app.add_url_rule("/course/add", "add_course", add_course, methods=["GET", "POST"])
    app.add_url_rule("/course/edit/<int:course_id>", "edit_course", edit_course, methods=["GET", "POST"])
    app.add_url_rule("/course/delete/<int:course_id>", "delete_course", delete_course, methods=["POST"])
    app.add_url_rule("/examinations", "examinations", examinations)
    app.add_url_rule("/examination/add", "add_examination", add_examination, methods=["GET", "POST"])
    app.add_url_rule("/examination/edit/<int:examination_id>", "edit_examination", edit_examination, methods=["GET", "POST"])
    app.add_url_rule("/examination/delete/<int:examination_id>", "delete_examination", delete_examination, methods=["POST"])
    app.add_url_rule("/examination/<int:examination_id>/rubrics", "manage_rubrics", manage_rubrics)
    app.add_url_rule("/rubric/add/<int:examination_id>", "add_rubric", add_rubric, methods=["GET", "POST"])
    app.add_url_rule("/rubric/edit/<int:rubric_id>", "edit_rubric", edit_rubric, methods=["GET", "POST"])
    app.add_url_rule("/rubric/delete/<int:rubric_id>", "delete_rubric", delete_rubric, methods=["POST"])
    app.add_url_rule("/examination/<int:examination_id>/settings", "examination_settings", examination_settings, methods=["GET", "POST"])
    app.add_url_rule("/examination/<int:examination_id>/toggle-slots", "toggle_slot_creation", toggle_slot_creation, methods=["POST"])
    app.add_url_rule("/examination/<int:examination_id>/reset-slots-override", "reset_slot_override", reset_slot_override, methods=["POST"])
    app.add_url_rule("/examination/<int:examination_id>/toggle-booking", "toggle_booking", toggle_booking, methods=["POST"])
    app.add_url_rule("/examination/<int:examination_id>/reset-booking-override", "reset_booking_override", reset_booking_override, methods=["POST"])
    app.add_url_rule("/admin/slots", "admin_slots", admin_slots)
    app.add_url_rule("/admin/slot/<int:slot_id>/change-examiner", "change_slot_examiner", change_slot_examiner, methods=["POST"])
    app.add_url_rule("/admin/bookings", "admin_bookings", admin_bookings)
    app.add_url_rule("/admin/booking/<int:booking_id>/reschedule", "reschedule_booking", reschedule_booking, methods=["GET", "POST"])
    app.add_url_rule("/admin/users", "admin_users", admin_users)
    app.add_url_rule("/course/<int:course_id>/resources", "course_resources", course_resources, methods=["GET", "POST"])
    app.add_url_rule("/course/resource/<int:resource_id>/delete", "delete_course_resource", delete_course_resource, methods=["POST"])
    app.add_url_rule("/admin/examiners/analytics", "admin_examiner_analytics", admin_examiner_analytics)
    app.add_url_rule("/admin/announcements", "admin_announcements", admin_announcements, methods=["GET", "POST"])
    app.add_url_rule("/admin/announcement/<int:announcement_id>/delete", "delete_announcement", delete_announcement, methods=["POST"])
