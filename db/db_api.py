from db import logins


def login_user(data):
    return logins.login_user(data)


def register_user(data):
    return logins.register_user(data)


def validate_auth_token(token):
    return logins.validate_auth_token(token)
