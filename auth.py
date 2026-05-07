from functools import wraps
from flask import jsonify, request
import config_loader
import cognito_auth


def get_current_user():
    """Return user from Cognito Bearer token, or None if unauthenticated."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:]
    username = cognito_auth.get_username(token)
    if not username:
        return None
    return config_loader.get_user_by_username(username)


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
