from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User, StudentProfile


def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("user_role")
    if role == "Admin":
        return redirect(url_for("admin_dashboard"))
    if role == "Examiner":
        return redirect(url_for("examiner_dashboard"))
    if role == "Student":
        return redirect(url_for("student_dashboard"))
    return redirect(url_for("login"))


def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if not name or not email or not password:
            flash("Please fill in all fields.")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.")
            return redirect(url_for("register"))

        new_user = User(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=generate_password_hash(password),
            role="Student",
            is_approved=True
        )
        db.session.add(new_user)
        db.session.flush()

        roll = email.split("@")[0].upper()
        if not StudentProfile.query.filter_by(roll_number=roll).first():
            db.session.add(StudentProfile(
                user_id=new_user.id,
                roll_number=roll,
                department="General Academic",
                year="1st Year"
            ))
        db.session.commit()

        flash("Account created. You can now log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


def examiner_register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if not name or not email or not password:
            flash("Please fill in all fields.")
            return redirect(url_for("examiner_register"))

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.")
            return redirect(url_for("examiner_register"))

        new_examiner = User(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=generate_password_hash(password),
            role="Examiner",
            is_approved=False
        )
        db.session.add(new_examiner)
        db.session.commit()

        flash("Registration received. Awaiting admin approval.")
        return redirect(url_for("examiner_register"))

    return render_template("examiner_register.html")


def login():
    if request.method == "POST":
        identifier = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=identifier.lower()).first()
        if not user and identifier:
            profile = StudentProfile.query.filter_by(roll_number=identifier.upper()).first()
            if profile:
                user = profile.user

        if not user or not check_password_hash(user.password_hash, password):
            flash("Incorrect email or password.")
            return redirect(url_for("login"))

        if not user.is_active:
            flash("Your account has been suspended.")
            return redirect(url_for("login"))

        if user.role == "Examiner" and not user.is_approved:
            flash("Your account is still pending verification.")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        session["user_role"] = user.role
        session["user_name"] = user.name

        if user.role == "Admin":
            return redirect(url_for("admin_dashboard"))
        if user.role == "Examiner":
            return redirect(url_for("examiner_dashboard"))
        return redirect(url_for("student_dashboard"))

    return render_template("login.html")


def logout():
    session.clear()
    flash("You have been signed out.")
    return redirect(url_for("login"))


def register_routes(app):
    app.add_url_rule("/", "index", index)
    app.add_url_rule("/register", "register", register, methods=["GET", "POST"])
    app.add_url_rule("/examiner_register", "examiner_register", examiner_register, methods=["GET", "POST"])
    app.add_url_rule("/login", "login", login, methods=["GET", "POST"])
    app.add_url_rule("/logout", "logout", logout)
