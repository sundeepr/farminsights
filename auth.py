from functools import wraps
from flask import session, jsonify, request
import config_loader


def get_current_user():
    """Return the current user dict from session, or None if not logged in."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    return config_loader.get_user_by_id(user_id)


def login_user(username, password):
    """Validate credentials and set session. Returns user dict or None."""
    user = config_loader.get_user_by_credentials(username, password)
    if user:
        session['user_id'] = user['id']
        session['role'] = user['role']
    return user


def logout_user():
    session.clear()


def get_redirect_for_user(user):
    """Return the landing URL for a user based on their role."""
    if user['role'] == 'admin':
        return '/admin'
    elif user['role'] == 'org_admin':
        return f'/org/{user["org_id"]}'
    else:
        farm_ids = user.get('farm_ids', [])
        if len(farm_ids) == 1:
            farm = config_loader.get_farm(farm_ids[0])
            if farm:
                org_ids = farm.get('org_ids', [])
                if org_ids:
                    return f'/org/{org_ids[0]}'
        # Fall back to first accessible org or admin
        orgs = config_loader.get_accessible_orgs(user)
        if orgs:
            return f'/org/{orgs[0]["id"]}'
        farms = config_loader.get_accessible_farms(user)
        if farms:
            return f'/farm/{farms[0]["id"]}'
        return '/'


def require_login(f):
    """Decorator for API routes that require authentication. Returns 401 JSON if not logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """Decorator factory for routes that require specific roles. Returns 403 JSON if unauthorized."""
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
    """Check if user has access to a specific farm."""
    if user['role'] == 'admin':
        return True
    accessible = config_loader.get_accessible_farms(user)
    return any(f['id'] == farm_id for f in accessible)


def can_access_org(user, org_id):
    """Check if user has access to a specific org."""
    if user['role'] == 'admin':
        return True
    accessible = config_loader.get_accessible_orgs(user)
    return any(o['id'] == org_id for o in accessible)
