from functools import wraps
from flask import jsonify, request
import config_loader
import cognito_auth

_COOKIE_NAME = 'access_token'


def get_current_user():
    """Return user dict or None. Checks in order:
    1. Authorization: Bearer <token>  — Android app
    2. access_token httpOnly cookie   — web browser
    """
    # 1. Bearer token (Android)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        username = cognito_auth.get_username(auth_header[7:])
        if username:
            return config_loader.get_user_by_username(username)

    # 2. httpOnly cookie (web browser)
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        username = cognito_auth.get_username(token)
        if username:
            return config_loader.get_user_by_username(username)

    return None


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            if user['role'] not in roles:
                return jsonify({'error': 'Forbidden'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def can_access_farm(user, farm_id):
    if user['role'] == 'admin':
        return True
    return any(f['id'] == farm_id for f in config_loader.get_accessible_farms(user))


def can_access_org(user, org_id):
    if user['role'] == 'admin':
        return True
    return any(o['id'] == org_id for o in config_loader.get_accessible_orgs(user))
