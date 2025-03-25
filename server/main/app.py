from flask import Flask, request, jsonify
from flask_cors import CORS
from db.db_api import *
from server.proxies.db_proxy import proxy_logins_api

app = Flask(__name__)
mode = "norm"
CORS(app, supports_credentials=True)


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()  # Expects JSON payload with "email" and "password"
    response, status, session_id = proxy_logins_api(login_user, data, mode)

    if status == 200:
        resp = jsonify(response)
        # Set the session_id cookie
        resp.set_cookie(
            'session_id',
            session_id,
            httponly=True,
            secure=True,  # set to True if using HTTPS
            samesite='Lax'  # adjust as needed
        )
        return resp, status

    return jsonify(response), status


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()  # Expects JSON payload with registration fields.
    response, status, session_id = proxy_logins_api(register_user, data, mode)

    if status == 200:
        resp = jsonify(response)
        # Set the session_id cookie upon successful registration
        resp.set_cookie(
            'session_id',
            session_id,
            httponly=True,
            secure=True,
            samesite='Lax'
        )
        return resp, status

    return jsonify(response), status


@app.route('/validate_session', methods=['GET'])
def validate_session_endpoint():
    # Read the session_id from the cookie instead of expecting it in JSON payload.
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"status": "failed", "reason": "No session cookie provided", "session_id": 0}), 401

    response, status, _ = proxy_logins_api(validate_session, session_id, mode)
    return jsonify(response), status


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
