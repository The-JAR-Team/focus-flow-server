from flask import Flask, request, jsonify

app = Flask(__name__)

# Dummy user data for demonstration
dummy_user = {
    "username": "admin",
    "password": "password123"
}


@app.route('/login', methods=['POST'])
def login():
    # Parse JSON payload from the request
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON payload"}), 400

    username = data.get("username")
    password = data.get("password")

    # Validate that both username and password were provided
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    # Check credentials against the dummy user data
    if username == dummy_user["username"] and password == dummy_user["password"]:
        return jsonify({"message": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401


if __name__ == '__main__':
    app.run(debug=True)
