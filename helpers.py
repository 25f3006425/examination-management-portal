from functools import wraps
from datetime import date, datetime
from flask import session, redirect, url_for, abort
from database import db
from models import User, Examination, Notification



def notify_user(user_id, title, message, category="info"):
    try:
        notif = Notification()
        notif.user_id = user_id
        notif.title = title
        notif.message = message
        notif.category = category
        db.session.add(notif)
        db.session.commit()
        return notif
    except Exception:
        db.session.rollback()
        return None


def notify_all(title, message, role="All", category="announcement"):
    try:
        query = User.query.filter_by(is_active=True)
        if role and role != "All":
            query = query.filter_by(role=role)
        for u in query.all():
            notif = Notification()
            notif.user_id = u.id
            notif.title = title
            notif.message = message
            notif.category = category
            db.session.add(notif)
        db.session.commit()
    except Exception:
        db.session.rollback()


def role_required(required_role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            uid = session.get("user_id")
            if not uid:
                return redirect(url_for("login"))

            user = db.session.get(User, uid) if hasattr(db.session, "get") else User.query.get(uid)
            if not user or not user.is_active:
                session.clear()
                return redirect(url_for("login"))

            if user.role != required_role:
                abort(403)

            if user.role == "Examiner" and not user.is_approved:
                session.clear()
                return redirect(url_for("login"))

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def update_examination_status(exam):
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if exam.status == "Completed":
        return

    slot_in_window = bool(exam.slot_creation_start and exam.slot_creation_end and (exam.slot_creation_start <= now <= exam.slot_creation_end))
    booking_in_window = bool(exam.booking_start and exam.booking_end and (exam.booking_start <= now <= exam.booking_end))

    if exam.slot_creation_override == "open":
        exam.slot_creation_open = True
    elif exam.slot_creation_override == "closed":
        exam.slot_creation_open = False
    else:
        exam.slot_creation_open = slot_in_window

    if exam.booking_override == "open":
        exam.booking_open = True
    elif exam.booking_override == "closed":
        exam.booking_open = False
    else:
        exam.booking_open = booking_in_window

    if exam.booking_open:
        exam.status = "Booking Open"
    elif exam.slot_creation_open:
        exam.status = "Slot Creation"
    elif exam.booking_end and now > exam.booking_end:
        if exam.slots:
            all_done = True
            for slot in exam.slots:
                if slot.date >= today:
                    all_done = False
                    break
                for b in slot.bookings:
                    if b.status not in ["Completed", "Cancelled"]:
                        all_done = False
                        break
            exam.status = "Completed" if all_done else "Closed"
        else:
            exam.status = "Closed"
    elif exam.slot_creation_start and now < exam.slot_creation_start:
        exam.status = "Upcoming"
    else:
        exam.status = "Draft"

    db.session.commit()


def refresh_all_examinations():
    try:
        for exam in Examination.query.all():
            update_examination_status(exam)
    except Exception:
        db.session.rollback()
