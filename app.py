from flask import Flask, render_template, request, redirect, url_for, flash, session
from database import db
from models import User
from functools import wraps
from flask import abort
from werkzeug.security import generate_password_hash, check_password_hash
import models

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///examination.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "zxcvbnmlkjhgfdsaqwertyuiop"

db.init_app(app)

with app.app_context():
    db.create_all()

from functools import wraps
from flask import abort

# Function to check user role
def role_required(required_role):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            # Check whether user is logged in
            if "user_id" not in session:
                return redirect(url_for("login"))

            # Get current user from database
            user = User.query.get(session["user_id"])

            if user is None:
                session.clear()
                return redirect(url_for("login"))

            # Check whether user has the required role
            if user.role != required_role:
                abort(403)

            # Check examiner approval
            if user.role == "Examiner" and not user.is_approved:
                session.clear()
                return redirect(url_for("login"))

            return function(*args, **kwargs)

        return wrapper

    return decorator

# Student Registration
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        # Check whether email already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("Email already registered!")
            return redirect(url_for("register"))

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Create new student
        new_user = User(
            name=name,
            email=email,
            password_hash=hashed_password,
            role="Student"
        )

        new_user.is_approved = True

        # Save student in database
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please login.")

        return redirect(url_for("login"))

    return render_template("register.html")

# Examiner Registration
@app.route("/examiner_register", methods=["GET", "POST"])
def examiner_register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        # Check whether email already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("Email already registered!")
            return redirect(url_for("examiner_register"))

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Create new examiner
        new_examiner = User(
            name=name,
            email=email,
            password_hash=hashed_password,
            role="Examiner"
        )

        # Examiner needs Admin approval
        new_examiner.is_approved = False

        # Save examiner in database
        db.session.add(new_examiner)
        db.session.commit()

        flash("Registration successful! Wait for Admin approval.")

        return redirect(url_for("examiner_register"))

    return render_template("examiner_register.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        # Find user using email
        user = User.query.filter_by(email=email).first()

        # Check whether user exists and password is correct
        if user and check_password_hash(user.password_hash, password):

            # Check whether examiner is approved
            if user.role == "Examiner" and not user.is_approved:
                flash("Your account is waiting for Admin approval.")
                return redirect(url_for("login"))

            # Store user information in session
            session["user_id"] = user.id
            session["user_role"] = user.role
            session["user_name"] = user.name

            flash("Login successful!")

            # Redirect according to role
            if user.role == "Admin":
                return redirect(url_for("admin_dashboard"))

            elif user.role == "Examiner":
                return redirect(url_for("examiner_dashboard"))

            elif user.role == "Student":
                return redirect(url_for("student_dashboard"))

        else:
            flash("Invalid email or password!")

    return render_template("login.html")

# Admin Dashboard
@app.route("/admin_dashboard")
@role_required("Admin")
def admin_dashboard():
    return render_template("admin_dashboard.html")


# Examiner Dashboard
@app.route("/examiner_dashboard")
@role_required("Examiner")
def examiner_dashboard():
    return render_template("examiner_dashboard.html")


# Student Dashboard
@app.route("/student_dashboard")
@role_required("Student")
def student_dashboard():
    return render_template("student_dashboard.html")

# Logout
@app.route("/logout")
def logout():

    # Clear all session information
    session.clear()

    flash("You have been logged out successfully.")

    # Redirect to login page
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)