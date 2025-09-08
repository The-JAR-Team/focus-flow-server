import os
import sys

# Insert project root directory into sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from flask import Flask
from flask_cors import CORS

from server.main.debug.debug import debug_bp
from server.main.health_check import health_check_bp
from server.main.users.user_handling import auth_bp
from server.main.videos.group_handling import groups_bp
from server.main.videos.playlists import playlist_bp
from server.main.videos.subscription import subscriptions_bp
from server.main.videos.ticket import tickets_bp
from server.main.videos.videos import videos_bp
from server.main.videos.watch_items import watch_items_bp

app = Flask(__name__)
CORS(app, supports_credentials=True)


# --- Blueprint Registration ---
# All blueprints are now registered with the '/api' prefix.

app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(playlist_bp, url_prefix='/api')
app.register_blueprint(videos_bp, url_prefix='/api')
app.register_blueprint(subscriptions_bp, url_prefix='/api')
app.register_blueprint(watch_items_bp, url_prefix='/api')
app.register_blueprint(tickets_bp, url_prefix='/api')

# Nested prefixes are now under /api as well
app.register_blueprint(groups_bp, url_prefix='/api/group')
app.register_blueprint(debug_bp, url_prefix='/api/debug')

# Health checks are often kept at the root for simplicity, so we leave it here.
app.register_blueprint(health_check_bp)


if __name__ == '__main__':
    # When running in Cloud Run, Google sets the PORT environment variable.
    # Use it if it exists, otherwise default to a local port like 5000.
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)