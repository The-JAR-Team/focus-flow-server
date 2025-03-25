from flask import Flask, request, jsonify
from flask_cors import CORS
from db.db_api import *
from server.proxies.db_proxy import proxy_logins_api

app = Flask(__name__)
mode = "norm"
CORS(app)

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()  # Expects JSON payload with "email" and "password"
    response, status = proxy_logins_api(login_user, data, mode)
    return jsonify(response), status


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()  # Expects JSON payload with registration fields.
    response, status = proxy_logins_api(register_user, data, mode)
    return jsonify(response), status


@app.route('/validate_token', methods=['POST'])
def validate_token():
    data = request.get_json()  # Expects JSON payload with "auth_token"
    token = data.get("auth_token")
    # Call the validate_auth_token API function; note that it expects a token, not a dict.
    response, status = proxy_logins_api(validate_auth_token, token, mode)
    return jsonify(response), status


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
