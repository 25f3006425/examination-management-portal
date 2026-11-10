
from database import db


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


# Course Model
class Course(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))

    def __init__(self, name: str, description: str = None):
        self.name = name
        self.description = description


# Examination Model
class Examination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"), nullable=False
    )
    def __init__(self, name: str, course_id: int = None    ):
        self.name = name
        self.course_id = course_id
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
        capacity: int = 1
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


# Examiner Profile Model
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

    def __init__(self,
        user_id: int,
        qualification: str = None,
        specialization: str = None
    ):
        self.user_id = user_id
        self.qualification = qualification
        self.specialization = specialization

# Evaluation
class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("booking.id"),
        unique=True,
        nullable=False
    )

    examiner_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    def __init__(self, booking_id: int, examiner_id: int = None):
        self.booking_id = booking_id
        self.examiner_id = examiner_id

    marks = db.Column(db.Integer)
    remarks = db.Column(db.String(500))
    status = db.Column(db.String(20), default="Pending")

    booking = db.relationship("Booking", backref="evaluation")
    examiner = db.relationship("User")


class EvaluationMark(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    evaluation_id = db.Column(
        db.Integer,
        db.ForeignKey("evaluation.id"),
        nullable=False
    )

    rubric_id = db.Column(
        db.Integer,
        db.ForeignKey("examination_rubric.id"),
        nullable=False
    )

    marks = db.Column(db.Integer, nullable=False)

    rubric = db.relationship("ExaminationRubric")

    evaluation = db.relationship(
        "Evaluation",
        backref="rubric_marks"
    )

    def __init__(
        self,
        evaluation_id: int,
        rubric_id: int,
        marks: int
    ):
        self.evaluation_id = evaluation_id
        self.rubric_id = rubric_id
        self.marks = marks



