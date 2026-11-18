from flask import Flask, session
from database import db
from models import (
    User, Course, Examination, ExaminationSlot, Booking,
    ExaminationRubric, Evaluation, ExaminerProfile, EvaluationMark,
    StudentProfile, CourseResource, Notification, Announcement
)
from helpers import (
    role_required, notify_user, notify_all,
    update_examination_status, refresh_all_examinations
)
from routes import init_routes


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///examination.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "zxcvbnmlkjhgfdsaqwertyuiop"

db.init_app(app)

with app.app_context():
    db.create_all()

init_routes(app)


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


if __name__ == "__main__":
    app.run(debug=True)
