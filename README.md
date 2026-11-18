# Examination Management Portal

A university examination scheduling and evaluation portal built with Flask and SQLite.

## Prerequisites

- Python 3.10+
- `pip`

## Installation & Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize the database and admin account**:
   ```bash
   python create_admin.py
   ```

## Running the Application

Start the development server:
```bash
python app.py
```

The portal will be live at:
```
http://127.0.0.1:5000
```

## User Roles & Authentication

| Role | Sign-in / Registration | Password | Notes |
|---|---|---|---|
| **Admin** | `admin@example.com` | `Admin@123` | Default administrator account created via `create_admin.py` |
| **Student** | Register at `/register` | User chosen | Can sign in with registered email or roll number |
| **Examiner** | Register at `/examiner_register` | User chosen | Requires approval by an Admin from the admin dashboard |
