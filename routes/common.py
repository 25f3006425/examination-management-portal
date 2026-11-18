from flask import render_template, redirect, url_for, flash, session
from database import db
from models import Course, Booking, Evaluation, Notification


def performance_analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("user_role")
    user_id = session["user_id"]

    if role == "Student":
        bookings = Booking.query.filter_by(student_id=user_id).all()
        evals = Evaluation.query.join(Booking).filter(
            Booking.student_id == user_id,
            Evaluation.status == "Completed"
        ).order_by(Evaluation.id.asc()).all()

        marks_list = [ev.marks for ev in evals if ev.marks is not None]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        highest_marks = max(marks_list) if marks_list else 0
        trend_labels = [ev.booking.slot.examination.name for ev in evals]
        trend_scores = [ev.marks for ev in evals]

        return render_template(
            "performance_analytics.html",
            role=role,
            attempts=len(bookings),
            completed_count=len(evals),
            avg_marks=avg_marks,
            highest_marks=highest_marks,
            trend_labels=trend_labels,
            trend_scores=trend_scores,
            evaluations=evals
        )

    if role == "Examiner":
        evals = Evaluation.query.filter_by(
            examiner_id=user_id,
            status="Completed"
        ).order_by(Evaluation.id.asc()).all()

        marks_list = [ev.marks for ev in evals if ev.marks is not None]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        highest_marks = max(marks_list) if marks_list else 0

        exam_names = list({ev.booking.slot.examination.name for ev in evals})
        exam_avg_marks = []
        for name in exam_names:
            sub = [ev.marks for ev in evals if ev.booking.slot.examination.name == name]
            exam_avg_marks.append(round(sum(sub) / len(sub), 1) if sub else 0)

        return render_template(
            "performance_analytics.html",
            role=role,
            attempts=len(evals),
            completed_count=len(evals),
            avg_marks=avg_marks,
            highest_marks=highest_marks,
            trend_labels=exam_names,
            trend_scores=exam_avg_marks,
            evaluations=evals
        )

    if role == "Admin":
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
            course_averages.append(round(sum(ev.marks for ev in c_evals) / len(c_evals), 1) if c_evals else 0)

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


def notifications():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_notifications = Notification.query.filter_by(
        user_id=session["user_id"]
    ).order_by(Notification.id.desc()).all()
    return render_template("notifications.html", notifications=user_notifications)


def mark_notification_read(notification_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    notif = Notification.query.filter_by(
        id=notification_id, user_id=session["user_id"]
    ).first_or_404()
    notif.is_read = True
    db.session.commit()
    return redirect(url_for("notifications"))


def mark_all_notifications_read():
    if "user_id" not in session:
        return redirect(url_for("login"))
    Notification.query.filter_by(
        user_id=session["user_id"], is_read=False
    ).update({"is_read": True})
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications"))


def register_routes(app):
    app.add_url_rule("/analytics", "performance_analytics", performance_analytics)
    app.add_url_rule("/notifications", "notifications", notifications)
    app.add_url_rule("/notification/<int:notification_id>/read", "mark_notification_read", mark_notification_read, methods=["POST"])
    app.add_url_rule("/notifications/read-all", "mark_all_notifications_read", mark_all_notifications_read, methods=["POST"])
