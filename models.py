from database import db
from datetime import datetime


# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def __init__(self, name: str, email: str, password_hash: str, role: str):
        self.name = name
        self.email = email
        self.password_hash = password_hash
        self.role = role

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


# Student Profile Model
class StudentProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False
    )
    roll_number = db.Column(db.String(50), unique=True, nullable=False)
    department = db.Column(db.String(100))
    year = db.Column(db.String(50))
    phone = db.Column(db.String(20))

    user = db.relationship(
        "User", backref=db.backref("student_profile", uselist=False)
    )

    def __init__(
        self,
        user_id: int,
        roll_number: str,
        department: str = None,
        year: str = None,
        phone: str = None,
    ):
        self.user_id = user_id
        self.roll_number = roll_number
        self.department = department
        self.year = year
        self.phone = phone


# Course Model
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))

    resources = db.relationship(
        "CourseResource", backref="course", cascade="all, delete-orphan"
    )

    def __init__(self, name: str, description: str = None):
        self.name = name
        self.description = description


# Course Resource Model
class CourseResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"), nullable=False
    )
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.String(30))

    def __init__(
        self,
        course_id: int,
        title: str,
        url: str,
        description: str = None,
        created_at: str = None,
    ):
        self.course_id = course_id
        self.title = title
        self.url = url
        self.description = description
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M")


# Examination Model
class Examination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"), nullable=False
    )

    # Examination status
    status = db.Column(db.String(30), default="Draft")

    # Examiner slot creation period
    slot_creation_start = db.Column(db.String(30))
    slot_creation_end = db.Column(db.String(30))

    slot_creation_open = db.Column(db.Boolean, default=False)
    booking_open = db.Column(db.Boolean, default=False)

    # Student booking period
    booking_start = db.Column(db.String(30))
    booking_end = db.Column(db.String(30))

    # Manual overrides: None = automatic, "open" = forced open, "closed" = forced closed
    slot_creation_override = db.Column(db.String(10), default=None)
    booking_override = db.Column(db.String(10), default=None)

    course = db.relationship("Course", backref="examinations")

    def __init__(self, name: str, course_id: int = None):
        self.name = name
        self.course_id = course_id


# Examination Rubric Model
class ExaminationRubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    examination_id = db.Column(
        db.Integer, db.ForeignKey("examination.id"), nullable=False
    )

    criterion = db.Column(db.String(200), nullable=False)
    marks = db.Column(db.Integer, nullable=False)

    examination = db.relationship("Examination", backref="rubrics")

    def __init__(self, examination_id: int, criterion: str = None, marks: int = None):
        self.examination_id = examination_id
        self.criterion = criterion
        self.marks = marks


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

    capacity = db.Column(db.Integer, default=1)

    def __init__(
        self,
        examination_id: int,
        examiner_id: int,
        date: str,
        time: str,
        capacity: int = 1,
    ):
        self.examination_id = examination_id
        self.examiner_id = examiner_id
        self.date = date
        self.time = time
        self.capacity = capacity


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

    def __init__(self, student_id: int, slot_id: int, status: str = "Booked"):
        self.student_id = student_id
        self.slot_id = slot_id
        self.status = status


# Examiner Profile Model
class ExaminerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False
    )

    qualification = db.Column(db.String(200))
    specialization = db.Column(db.String(200))

    user = db.relationship(
        "User", backref=db.backref("examiner_profile", uselist=False)
    )

    def __init__(
        self,
        user_id: int,
        qualification: str = None,
        specialization: str = None,
    ):
        self.user_id = user_id
        self.qualification = qualification
        self.specialization = specialization


# Evaluation Model
class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer, db.ForeignKey("booking.id"), unique=True, nullable=False
    )

    examiner_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )

    marks = db.Column(db.Integer)
    remarks = db.Column(db.String(500))
    status = db.Column(db.String(20), default="Pending")

    booking = db.relationship("Booking", backref=db.backref("evaluation", uselist=False))
    examiner = db.relationship("User")

    def __init__(self, booking_id: int, examiner_id: int = None):
        self.booking_id = booking_id
        self.examiner_id = examiner_id


# Evaluation Mark Model
class EvaluationMark(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    evaluation_id = db.Column(
        db.Integer, db.ForeignKey("evaluation.id"), nullable=False
    )

    rubric_id = db.Column(
        db.Integer, db.ForeignKey("examination_rubric.id"), nullable=False
    )

    marks = db.Column(db.Integer, nullable=False)

    rubric = db.relationship("ExaminationRubric")
    evaluation = db.relationship("Evaluation", backref="rubric_marks")

    def __init__(self, evaluation_id: int, rubric_id: int, marks: int):
        self.evaluation_id = evaluation_id
        self.rubric_id = rubric_id
        self.marks = marks


# Notification Model
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), default="info")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(30))

    user = db.relationship(
        "User",
        backref=db.backref(
            "notifications",
            cascade="all, delete-orphan",
            order_by="desc(Notification.id)",
        ),
    )

    def __init__(
        self,
        user_id: int,
        title: str,
        message: str,
        category: str = "info",
        created_at: str = None,
    ):
        self.user_id = user_id
        self.title = title
        self.message = message
        self.category = category
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M")


# Announcement Model
class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    target_role = db.Column(db.String(50), default="All")
    event_date = db.Column(db.String(30))
    created_at = db.Column(db.String(30))

    def __init__(
        self,
        title: str,
        content: str,
        target_role: str = "All",
        event_date: str = None,
        created_at: str = None,
    ):
        self.title = title
        self.content = content
        self.target_role = target_role
        self.event_date = event_date
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M")
