from flask import Flask, request, jsonify

from db.db_api import get_user


def get_authenticated_user():
    """
    Reads the session_id cookie, validates the session,
    and returns the associated user_id.
    Returns (user_id, status_code) tuple.
    """
    session_id = request.cookies.get('session_id')
    if not session_id:
        return 0, 401  # No session cookie provided.
    user_id, status = get_user(session_id)
    return user_id, status
