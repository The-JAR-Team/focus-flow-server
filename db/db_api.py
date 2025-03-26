from db import user_management, playlists_management

def login_user(data):
    return user_management.login_user(data)

def register_user(data):
    return user_management.register_user(data)

def validate_session(session_id):
    return user_management.validate_session(session_id)

def get_user(session_id):
    return user_management.get_user(session_id)

def create_playlist(user_id, playlist_name, playlist_permission):
    return playlists_management.create_playlist(user_id, playlist_name, playlist_permission)

def delete_playlist(user_id, playlist_id):
    return playlists_management.delete_playlist(user_id, playlist_id)

def get_all_user_playlists(user_id):
    return playlists_management.get_all_user_playlists(user_id)

def update_playlist_permission(user_id, playlist_id, new_permission):
    return playlists_management.update_playlist_permission(user_id, playlist_id, new_permission)
