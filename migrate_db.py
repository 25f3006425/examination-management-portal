import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "examination.db")

def run_migration():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Update examination table columns
    exam_cols = [c[1] for c in cur.execute("PRAGMA table_info(examination);").fetchall()]
    if "slot_creation_override" not in exam_cols:
        cur.execute("ALTER TABLE examination ADD COLUMN slot_creation_override VARCHAR(10);")
        print("Added slot_creation_override to examination.")
    if "booking_override" not in exam_cols:
        cur.execute("ALTER TABLE examination ADD COLUMN booking_override VARCHAR(10);")
        print("Added booking_override to examination.")

    # 2. Create student_profile table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        roll_number VARCHAR(50) UNIQUE NOT NULL,
        department VARCHAR(100),
        year VARCHAR(50),
        phone VARCHAR(20),
        FOREIGN KEY (user_id) REFERENCES user(id)
    );
    """)

    # 3. Create course_resource table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS course_resource (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        title VARCHAR(200) NOT NULL,
        url VARCHAR(500) NOT NULL,
        description VARCHAR(500),
        created_at VARCHAR(30),
        FOREIGN KEY (course_id) REFERENCES course(id)
    );
    """)

    # 4. Create notification table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notification (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title VARCHAR(150) NOT NULL,
        message VARCHAR(500) NOT NULL,
        category VARCHAR(50) DEFAULT 'info',
        is_read BOOLEAN DEFAULT 0,
        created_at VARCHAR(30),
        FOREIGN KEY (user_id) REFERENCES user(id)
    );
    """)

    # 5. Create announcement table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS announcement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title VARCHAR(200) NOT NULL,
        content TEXT NOT NULL,
        target_role VARCHAR(50) DEFAULT 'All',
        event_date VARCHAR(30),
        created_at VARCHAR(30)
    );
    """)

    conn.commit()

    # 6. Ensure existing student has profile
    cur.execute("SELECT id, email, name FROM user WHERE role = 'Student';")
    students = cur.fetchall()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    for s_id, s_email, s_name in students:
        cur.execute("SELECT id FROM student_profile WHERE user_id = ?;", (s_id,))
        if not cur.fetchone():
            roll = s_email.split("@")[0].upper()
            cur.execute("""
            INSERT INTO student_profile (user_id, roll_number, department, year, phone)
            VALUES (?, ?, ?, ?, ?);
            """, (s_id, roll, "Data Science and Applications", "3rd Year", "9876543210"))
            print(f"Created profile for existing student {s_name} ({roll})")

    # 7. Add pre-existing college students if not present
    preexisting_students = [
        ("Aarav Sharma", "aarav.sharma@college.edu", "student123", "23CS101", "Computer Science & Engineering", "3rd Year", "9811223344"),
        ("Priya Patel", "priya.patel@college.edu", "student123", "23DS102", "Data Science and Applications", "3rd Year", "9822334455"),
        ("Rohan Verma", "rohan.verma@college.edu", "student123", "24EE103", "Electrical Engineering", "2nd Year", "9833445566"),
        ("Ananya Iyer", "ananya.iyer@college.edu", "student123", "24ME104", "Mechanical Engineering", "2nd Year", "9844556677"),
        ("Kavya Nair", "kavya.nair@college.edu", "student123", "25CS105", "Computer Science & Engineering", "1st Year", "9855667788"),
    ]

    for name, email, pwd, roll, dept, year, phone in preexisting_students:
        cur.execute("SELECT id FROM user WHERE email = ?;", (email,))
        row = cur.fetchone()
        if not row:
            hashed = generate_password_hash(pwd)
            cur.execute("""
            INSERT INTO user (name, email, password_hash, role, is_approved, is_active)
            VALUES (?, ?, ?, 'Student', 1, 1);
            """, (name, email, hashed))
            new_uid = cur.lastrowid
            cur.execute("""
            INSERT INTO student_profile (user_id, roll_number, department, year, phone)
            VALUES (?, ?, ?, ?, ?);
            """, (new_uid, roll, dept, year, phone))
            print(f"Added pre-existing student: {name} ({roll})")

    # 8. Add sample announcement if none exist
    cur.execute("SELECT COUNT(*) FROM announcement;")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO announcement (title, content, target_role, event_date, created_at)
        VALUES (?, ?, ?, ?, ?);
        """, (
            "Mid-Term Examination Guidelines & Schedule Published",
            "All students and examiners are requested to check their examination schedules and guidelines. Slot creation and booking must adhere strictly to the published timelines.",
            "All",
            datetime.now().strftime("%Y-%m-%d"),
            now_str
        ))
        print("Created initial announcement.")

    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    run_migration()
