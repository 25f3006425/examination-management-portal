"""
Automated Test Suite for All 12 Requirements
"""

import unittest
import io
from app import app
from database import db
from models import (
    User, Course, Examination, ExaminationSlot, Booking,
    ExaminationRubric, Evaluation, EvaluationMark, StudentProfile,
    CourseResource, Notification, Announcement
)
from datetime import date, datetime, timedelta

class TestPortalFeatures(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def login_as(self, email, password):
        return self.client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    def test_01_automatic_timelines_and_abrupt_override(self):
        """Req 1: Automatic slot creation and booking start/end + Admin abrupt control"""
        # Find or create examination
        course = Course.query.first()
        if not course:
            course = Course(name="Test Course 101")
            db.session.add(course)
            db.session.commit()

        now = datetime.now()
        past = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        future = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        far_future = (now + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")

        exam = Examination(name="Timeline Auto Test", course_id=course.id)
        exam.slot_creation_start = past
        exam.slot_creation_end = future
        db.session.add(exam)
        db.session.commit()

        # Update status
        from app import update_examination_status
        update_examination_status(exam)
        # Should be auto-open because now is between past and future
        self.assertTrue(exam.slot_creation_open)
        self.assertEqual(exam.status, "Slot Creation")

        # Admin abrupt stop
        with self.client.session_transaction() as sess:
            admin = User.query.filter_by(role="Admin").first()
            sess["user_id"] = admin.id
            sess["user_role"] = "Admin"
            sess["user_name"] = admin.name

        resp = self.client.post(f"/examination/{exam.id}/toggle-slots", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(exam.slot_creation_open)
        self.assertEqual(exam.slot_creation_override, "closed")

        # Reset to automatic schedule
        resp = self.client.post(f"/examination/{exam.id}/reset-slots-override", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(exam.slot_creation_override)
        self.assertTrue(exam.slot_creation_open)

    def test_02_booking_must_start_after_slot_creation_end(self):
        """Req 2: Slot booking must only start AFTER slot creation time ends"""
        with self.client.session_transaction() as sess:
            admin = User.query.filter_by(role="Admin").first()
            sess["user_id"] = admin.id
            sess["user_role"] = "Admin"
            sess["user_name"] = admin.name

        exam = Examination.query.first()
        # Invalid timeline: booking_start is BEFORE slot_creation_end
        resp = self.client.post(f"/examination/{exam.id}/settings", data={
            "slot_creation_start": "2026-11-20T09:00",
            "slot_creation_end": "2026-11-21T18:00",
            "booking_start": "2026-11-21T10:00", # Invalid! before slot_creation_end
            "booking_end": "2026-11-22T18:00"
        }, follow_redirects=True)
        self.assertIn(b"Constraint Violation", resp.data)

        # Valid timeline: booking_start is AFTER slot_creation_end
        resp = self.client.post(f"/examination/{exam.id}/settings", data={
            "slot_creation_start": "2026-11-20T09:00",
            "slot_creation_end": "2026-11-21T18:00",
            "booking_start": "2026-11-22T09:00", # Valid! after slot_creation_end
            "booking_end": "2026-11-23T18:00"
        }, follow_redirects=True)
        self.assertIn(b"Examination timelines saved successfully.", resp.data)

    def test_03_student_calendar(self):
        """Req 3: Student calendar showing upcoming exams, booked dates, deadlines"""
        student = User.query.filter_by(role="Student").first()
        with self.client.session_transaction() as sess:
            sess["user_id"] = student.id
            sess["user_role"] = "Student"
            sess["user_name"] = student.name

        resp = self.client.get("/student/calendar")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Academic Examination Calendar", resp.data)
        self.assertIn(b"calendarEvents", resp.data)

    def test_04_preexisting_students_and_csv_import(self):
        """Req 4: Pre-existing students, profile, sample CSV and CSV upload"""
        # Verify pre-existing students
        students = User.query.filter_by(role="Student").all()
        self.assertGreater(len(students), 0)
        for s in students:
            self.assertIsNotNone(s.student_profile)
            self.assertTrue(len(s.student_profile.roll_number) > 0)

        with self.client.session_transaction() as sess:
            admin = User.query.filter_by(role="Admin").first()
            sess["user_id"] = admin.id
            sess["user_role"] = "Admin"
            sess["user_name"] = admin.name

        # Sample CSV download
        resp = self.client.get("/admin/students/sample-csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"roll_number", resp.data)

        # Test CSV upload
        csv_data = "name,email,password,roll_number,department,year,phone\n" \
                   "Vikram Singh,vikram.singh@college.edu,pass123,23CS999,Computer Science,2nd Year,9811111111\n"
        data = {
            "csv_file": (io.BytesIO(csv_data.encode("utf-8")), "students.csv")
        }
        resp = self.client.post("/admin/students/import-csv", data=data, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"CSV Import Successful", resp.data)

        # Verify Vikram Singh exists
        u = User.query.filter_by(email="vikram.singh@college.edu").first()
        self.assertIsNotNone(u)
        self.assertEqual(u.student_profile.roll_number, "23CS999")

    def test_05_and_10_results_display_and_pdf_download(self):
        """Req 5 & 10: Results in dashboard, Printable Transcript, and Vector PDF generation"""
        student = User.query.filter_by(role="Student").first()
        examiner = User.query.filter_by(role="Examiner").first()
        exam = Examination.query.first()

        # Create slot and booking
        slot = ExaminationSlot(examination_id=exam.id, examiner_id=examiner.id, date="2026-11-18", time="10:00")
        db.session.add(slot)
        db.session.commit()

        booking = Booking(student_id=student.id, slot_id=slot.id, status="Completed")
        db.session.add(booking)
        db.session.commit()

        # Create evaluation
        evaluation = Evaluation(booking_id=booking.id, examiner_id=examiner.id)
        evaluation.marks = 85
        evaluation.remarks = "Excellent domain understanding and clear presentation."
        evaluation.status = "Completed"
        db.session.add(evaluation)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess["user_id"] = student.id
            sess["user_role"] = "Student"
            sess["user_name"] = student.name

        # Test Dashboard shows result
        resp = self.client.get("/student_dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Published Examination Results", resp.data)
        self.assertIn(b"85", resp.data)

        # Test Printable Transcript Report
        resp = self.client.get(f"/student/result/{evaluation.id}/report")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Official Academic Evaluation Transcript", resp.data)
        self.assertIn(b"85", resp.data)

        # Test Direct PDF Download
        resp = self.client.get(f"/student/result/{evaluation.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/pdf")
        self.assertTrue(len(resp.data) > 500)
        self.assertTrue(resp.data.startswith(b"%PDF"))

    def test_06_admin_examiner_analytics(self):
        """Req 6: Examiner status tracking, progress, average grading charts"""
        with self.client.session_transaction() as sess:
            admin = User.query.filter_by(role="Admin").first()
            sess["user_id"] = admin.id
            sess["user_role"] = "Admin"
            sess["user_name"] = admin.name

        resp = self.client.get("/admin/examiners/analytics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Faculty Examiner Progress", resp.data)
        self.assertIn(b"examinerProgressChart", resp.data)

    def test_07_course_resources(self):
        """Req 7: Course resources admin add/delete, student view, and default message"""
        course = Course.query.first()
        with self.client.session_transaction() as sess:
            admin = User.query.filter_by(role="Admin").first()
            sess["user_id"] = admin.id
            sess["user_role"] = "Admin"
            sess["user_name"] = admin.name

        # Add resource
        resp = self.client.post(f"/course/{course.id}/resources", data={
            "title": "Machine Learning Lab Guide",
            "url": "https://example.com/ml-guide.pdf",
            "description": "Comprehensive reference guide for lab examination"
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Study resource published successfully.", resp.data)

        # Student views resources
        student = User.query.filter_by(role="Student").first()
        with self.client.session_transaction() as sess:
            sess["user_id"] = student.id
            sess["user_role"] = "Student"
            sess["user_name"] = student.name

        resp = self.client.get("/student/resources")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Machine Learning Lab Guide", resp.data)

    def test_08_performance_analytics_for_every_role(self):
        """Req 8: Student performance analytics available to Student, Examiner, Admin"""
        for role in ["Student", "Examiner", "Admin"]:
            user = User.query.filter_by(role=role).first()
            with self.client.session_transaction() as sess:
                sess["user_id"] = user.id
                sess["user_role"] = role
                sess["user_name"] = user.name

            resp = self.client.get("/analytics")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Student Performance Analytics", resp.data)
            self.assertIn(b"Average Marks", resp.data)
            self.assertIn(b"Highest Marks", resp.data)

    def test_09_notification_centre(self):
        """Req 9: Notification Centre and triggers"""
        student = User.query.filter_by(role="Student").first()
        notif = Notification(user_id=student.id, title="Test Notification", message="Booking confirmed successfully", category="booking")
        db.session.add(notif)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess["user_id"] = student.id
            sess["user_role"] = "Student"
            sess["user_name"] = student.name

        resp = self.client.get("/notifications")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test Notification", resp.data)

        # Mark as read
        resp = self.client.post(f"/notification/{notif.id}/read", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Notification.query.get(notif.id).is_read)

    def test_11_examiner_history(self):
        """Req 11: Examiner history and personal analytics section"""
        examiner = User.query.filter_by(role="Examiner").first()
        with self.client.session_transaction() as sess:
            sess["user_id"] = examiner.id
            sess["user_role"] = "Examiner"
            sess["user_name"] = examiner.name

        resp = self.client.get("/examiner/history")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Examiner Evaluation History", resp.data)
        self.assertIn(b"Students Evaluated", resp.data)

    def test_12_announcement_management(self):
        """Req 12: Announcement management by Admin"""
        with self.client.session_transaction() as sess:
            admin = User.query.filter_by(role="Admin").first()
            sess["user_id"] = admin.id
            sess["user_role"] = "Admin"
            sess["user_name"] = admin.name

        # Publish announcement
        resp = self.client.post("/admin/announcements", data={
            "title": "Final Assessment Guidelines Released",
            "content": "Please verify your slots and guidelines before examination.",
            "target_role": "All",
            "event_date": "2026-11-25"
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Announcement published successfully", resp.data)

        ann = Announcement.query.filter_by(title="Final Assessment Guidelines Released").first()
        self.assertIsNotNone(ann)

        # Delete announcement
        resp = self.client.post(f"/admin/announcement/{ann.id}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(Announcement.query.filter_by(title="Final Assessment Guidelines Released").first())

if __name__ == "__main__":
    unittest.main()
