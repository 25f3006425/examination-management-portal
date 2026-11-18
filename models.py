from datetime import datetime
from database import db


class BaseModel(db.Model):
    __abstract__ = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class User(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    @property
    def roll_number(self):
        return self.student_profile.roll_number if self.student_profile else ""

    @property
    def department(self):
        return self.student_profile.department if self.student_profile else ""

    @property
    def year(self):
        return self.student_profile.year if self.student_profile else ""

    @property
    def phone(self):
        return self.student_profile.phone if self.student_profile else ""


class StudentProfile(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    roll_number = db.Column(db.String(50), unique=True, nullable=False)
    department = db.Column(db.String(100))
    year = db.Column(db.String(50))
    phone = db.Column(db.String(20))

    user = db.relationship("User", backref=db.backref("student_profile", uselist=False))


class Course(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))

    resources = db.relationship("CourseResource", backref="course", cascade="all, delete-orphan")


class CourseResource(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.String(30), default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))


class Examination(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)

    status = db.Column(db.String(30), default="Draft")
    slot_creation_start = db.Column(db.String(30))
    slot_creation_end = db.Column(db.String(30))
    slot_creation_open = db.Column(db.Boolean, default=False)
    booking_open = db.Column(db.Boolean, default=False)

    booking_start = db.Column(db.String(30))
    booking_end = db.Column(db.String(30))

    slot_creation_override = db.Column(db.String(10), default=None)
    booking_override = db.Column(db.String(10), default=None)

    course = db.relationship("Course", backref="examinations")


class ExaminationRubric(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    criterion = db.Column(db.String(200), nullable=False)
    marks = db.Column(db.Integer, nullable=False)

    examination = db.relationship("Examination", backref="rubrics")


class ExaminationSlot(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, default=1)

    examination = db.relationship("Examination", backref="slots")
    examiner = db.relationship("User", backref="assigned_slots")


class Booking(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey("examination_slot.id"), nullable=False)
    status = db.Column(db.String(20), default="Booked")

    student = db.relationship("User", backref="bookings")
    slot = db.relationship("ExaminationSlot", backref="bookings")


class ExaminerProfile(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    qualification = db.Column(db.String(200))
    specialization = db.Column(db.String(200))

    user = db.relationship("User", backref=db.backref("examiner_profile", uselist=False))


class Evaluation(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), unique=True, nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    marks = db.Column(db.Integer)
    remarks = db.Column(db.String(500))
    status = db.Column(db.String(20), default="Pending")

    booking = db.relationship("Booking", backref=db.backref("evaluation", uselist=False))
    examiner = db.relationship("User")


class EvaluationMark(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("evaluation.id"), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey("examination_rubric.id"), nullable=False)
    marks = db.Column(db.Integer, nullable=False)

    rubric = db.relationship("ExaminationRubric")
    evaluation = db.relationship("Evaluation", backref="rubric_marks")


class Notification(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), default="info")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(30), default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    user = db.relationship(
        "User",
        backref=db.backref(
            "notifications",
            cascade="all, delete-orphan",
            order_by="desc(Notification.id)",
        ),
    )


class Announcement(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    target_role = db.Column(db.String(50), default="All")
    event_date = db.Column(db.String(30))
    created_at = db.Column(db.String(30), default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
