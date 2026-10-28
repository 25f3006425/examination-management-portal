
from database import db


# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    def __init__(self, name: str, email: str, password_hash: str, role: str):
        self.name = name
        self.email = email
        self.password_hash = password_hash
        self.role = role    


# Course Model
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))


# Examination Model
class Examination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"), nullable=False
    )

    course = db.relationship("Course", backref="examinations")


# Examination Rubric Model
class ExaminationRubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    examination_id = db.Column(
        db.Integer, db.ForeignKey("examination.id"), nullable=False
    )

    criterion = db.Column(db.String(200), nullable=False)
    marks = db.Column(db.Integer, nullable=False)

    examination = db.relationship("Examination", backref="rubrics")


# Examination Slot Model
class ExaminationSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    examination_id = db.Column(
        db.Integer, db.ForeignKey("examination.id"), nullable=False
    )

    examiner_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )

    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)

    examination = db.relationship("Examination", backref="slots")

    examiner = db.relationship("User", backref="assigned_slots")


# Booking Model
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )

    slot_id = db.Column(
        db.Integer, db.ForeignKey("examination_slot.id"), nullable=False
    )

    status = db.Column(db.String(20), default="Booked")

    student = db.relationship("User", backref="bookings")

    slot = db.relationship("ExaminationSlot", backref="bookings")


# 7. Examiner Profile Model
class ExaminerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"),
        unique=True, nullable=False
    )

    qualification = db.Column(db.String(200))
    specialization = db.Column(db.String(200))

    user = db.relationship(
        "User",
        backref=db.backref("examiner_profile", uselist=False)
    )
