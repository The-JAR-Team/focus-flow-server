from flask import Flask
from server.main.users.user_handling import auth_bp
from server.main.videos.playlists import playlist_bp
from flask_cors import CORS


app = Flask(__name__)
mode = "norm"
CORS(app, supports_credentials=True)


app.register_blueprint(auth_bp)
app.register_blueprint(playlist_bp)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
