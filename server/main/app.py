import os
import sys

from server.main.health_check import health_check_bp
from server.main.videos.group_handling import groups_bp
from server.main.videos.ticket import tickets_bp

# Insert project root directory into sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from flask import Flask
from server.main.debug.debug import debug_bp
from server.main.users.user_handling import auth_bp
from server.main.videos.playlists import playlist_bp
from flask_cors import CORS
from server.main.videos.subscription import subscriptions_bp
from server.main.videos.videos import videos_bp
from server.main.videos.watch_items import watch_items_bp

app = Flask(__name__)
CORS(app, supports_credentials=True)


app.register_blueprint(auth_bp)
app.register_blueprint(playlist_bp)
app.register_blueprint(videos_bp)
app.register_blueprint(subscriptions_bp)
app.register_blueprint(watch_items_bp)
app.register_blueprint(health_check_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(groups_bp, url_prefix='/group')
app.register_blueprint(debug_bp, url_prefix='/debug')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
