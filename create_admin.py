from app import app
from database import db
from models import User
from werkzeug.security import generate_password_hash


with app.app_context():

    admin = User.query.filter_by(role="Admin").first()

    if not admin:
        admin = User(
            name="Admin",
            email="admin@example.com",
            password_hash=generate_password_hash("Admin@123"),
            role="Admin"
        )

        db.session.add(admin)
        db.session.commit()

        print("Admin created successfully!")
    else:
        print("Admin already exists!")