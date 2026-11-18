from routes.auth import register_routes as register_auth_routes
from routes.admin import register_routes as register_admin_routes
from routes.examiner import register_routes as register_examiner_routes
from routes.student import register_routes as register_student_routes
from routes.common import register_routes as register_common_routes


def init_routes(app):
    register_auth_routes(app)
    register_admin_routes(app)
    register_examiner_routes(app)
    register_student_routes(app)
    register_common_routes(app)
