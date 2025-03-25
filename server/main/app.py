from flask import Flask
from users.user_handling import auth_bp
from flask_cors import CORS


app = Flask(__name__)
mode = "norm"
CORS(app, supports_credentials=True)


app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(playlist_bp, url_prefix='/api')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
