# subscriptions.py
from flask import Blueprint, request, jsonify
from db.db_api import subscribe_playlist, unsubscribe_playlist
from server.main.utils import get_authenticated_user

subscriptions_bp = Blueprint('subscriptions', __name__)


@subscriptions_bp.route('/subscriptions/subscribe', methods=['POST'])
def subscribe():
    """
    Endpoint to subscribe a user to a playlist.

    Expected JSON payload:
      {
         "email": <str>,        # Email of the subscriber
         "playlist_id": <int>     # The target playlist's ID
      }

    The authenticated owner (retrieved from the session via get_authenticated_user)
    is used to verify that the playlist is owned by them before subscribing the user.
    """
    owner_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    response, code = subscribe_playlist(owner_id, data)
    return jsonify(response), code


@subscriptions_bp.route('/subscriptions/unsubscribe', methods=['POST'])
def unsubscribe():
    """
    Endpoint to unsubscribe a user from a playlist.

    Expected JSON payload:
      {
         "email": <str>,        # Email of the subscriber
         "playlist_id": <int>     # The target playlist's ID
      }

    The authenticated owner (retrieved via get_authenticated_user) is used to ensure that
    the subscription being removed belongs to a playlist owned by them.
    """
    owner_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    response, code = unsubscribe_playlist(owner_id, data)
    return jsonify(response), code
