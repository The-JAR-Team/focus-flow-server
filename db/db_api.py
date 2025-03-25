from db import user_management


def login_user(data):
    return user_management.login_user(data)


def register_user(data):
    return user_management.register_user(data)


def validate_session(session_id):
    return user_management.validate_session(session_id)


def get_user(session_id):
    return user_management.get_user(session_id)
