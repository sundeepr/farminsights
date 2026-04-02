import os
import json
import glob

from datetime import datetime
from flask import Flask, render_template, jsonify, send_from_directory, request, redirect
from werkzeug.utils import secure_filename

import config_loader
import auth as auth_module
import weather as weather_module

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')


# ---------------------------------------------------------------------------
# Auth API routes
# ---------------------------------------------------------------------------

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    user = auth_module.login_user(data.get('username', ''), data.get('password', ''))
    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401
    redirect_url = auth_module.get_redirect_for_user(user)
    return jsonify({'ok': True, 'role': user['role'], 'redirect_url': redirect_url})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    auth_module.logout_user()
    return jsonify({'ok': True})


@app.route('/api/me')
def api_me():
    user = auth_module.get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify({'id': user['id'], 'username': user['username'],
                    'display_name': user.get('display_name', user['username']), 'role': user['role']})


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route('/login')
def login_page():
    user = auth_module.get_current_user()
    if user:
        return redirect(auth_module.get_redirect_for_user(user))
    return render_template('login.html', year=datetime.now().year)


@app.route('/')
def index():
    user = auth_module.get_current_user()
    if user:
        return redirect(auth_module.get_redirect_for_user(user))
    return redirect('/login')


@app.route('/admin')
def admin_dashboard():
    user = auth_module.get_current_user()
    if not user:
        return redirect('/login')
    if user['role'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    nav_context = config_loader.build_nav_context(user)
    cfg = config_loader.load_config()
    return render_template('admin_dashboard.html', user=user, nav_context=nav_context,
                           page_title='Admin Dashboard',
                           total_orgs=len(cfg['organizations']),
                           total_farms=len(cfg['farms']),
                           total_users=len(cfg['users']))


@app.route('/org/<org_id>')
def org_dashboard(org_id):
    user = auth_module.get_current_user()
    if not user:
        return redirect('/login')
    if not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    org = config_loader.get_org(org_id)
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    nav_context = config_loader.build_nav_context(user, current_org_id=org_id)
    breadcrumb = config_loader.get_org_ancestry(org_id)
    return render_template('org_dashboard.html', user=user, nav_context=nav_context,
                           org=org, breadcrumb=breadcrumb,
                           page_title=org['name'])


@app.route('/farm/<farm_id>')
def farm_map(farm_id):
    user = auth_module.get_current_user()
    if not user:
        return redirect('/login')
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    org_ids = farm.get('org_ids', [])
    context_org_id = request.args.get('org') or (org_ids[0] if org_ids else None)
    if context_org_id and context_org_id not in org_ids:
        context_org_id = org_ids[0] if org_ids else None
    breadcrumb = config_loader.get_org_ancestry(context_org_id) if context_org_id else []
    nav_context = config_loader.build_nav_context(user, current_farm_id=farm_id,
                                                   current_org_id=context_org_id)
    return render_template('farm_map.html', user=user, nav_context=nav_context,
                           farm=farm, breadcrumb=breadcrumb,
                           page_title=farm['name'])


# ---------------------------------------------------------------------------
# Data API routes
# ---------------------------------------------------------------------------

@app.route('/api/files')
def get_files():
    farm_id = request.args.get('farm_id')
    if not farm_id:
        return jsonify({'error': 'farm_id parameter required'}), 400
    user = auth_module.get_current_user()
    if user and not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    data_files = glob.glob(os.path.join(farm['data_folder'], '*.json'))
    files = []
    for f in sorted(data_files, reverse=True):
        filename = os.path.basename(f)
        display_name = filename.replace('.json', '').replace('_', ' ')
        files.append({'filename': filename, 'display': display_name})
    return jsonify(files)


@app.route('/api/data/<farm_id>/<filename>')
def get_data(farm_id, filename):
    user = auth_module.get_current_user()
    if user and not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    # Prevent path traversal
    if '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    filepath = os.path.join(farm['data_folder'], filename)
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({'error': 'Data file not found'}), 404
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON data'}), 500


@app.route('/api/org/<org_id>/summary')
def org_summary(org_id):
    user = auth_module.get_current_user()
    if user and not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    org = config_loader.get_org(org_id)
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    summary = config_loader.compute_org_summary(org_id)
    # Normal users only see their own farms
    if user and user['role'] == 'user':
        accessible_ids = {f['id'] for f in config_loader.get_accessible_farms(user)}
        summary['farms'] = [f for f in summary['farms'] if f['farm_id'] in accessible_ids]
        summary['farm_count'] = len(summary['farms'])
    return jsonify(summary)


@app.route('/api/admin/orgs/list')
@auth_module.require_role('admin')
def admin_orgs_list():
    """Lightweight list of all orgs for dropdowns (admin only)."""
    cfg = config_loader.load_config()
    return jsonify([{'id': o['id'], 'name': o['name'], 'parent_id': o.get('parent_id')}
                    for o in cfg['organizations']])


@app.route('/api/admin/farms/list')
@auth_module.require_role('admin')
def admin_farms_list():
    """Lightweight list of all farms for dropdowns (admin only)."""
    cfg = config_loader.load_config()
    return jsonify([{'id': f['id'], 'name': f['name'], 'org_ids': f.get('org_ids', [])}
                    for f in cfg['farms']])


@app.route('/api/org/<org_id>/orgs/list')
@auth_module.require_login
def org_orgs_list(org_id):
    """Orgs within this org's subtree — for org_admin dropdowns."""
    user = auth_module.get_current_user()
    if not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    org_ids = config_loader.get_org_subtree_ids(org_id)
    cfg = config_loader.load_config()
    orgs = [{'id': o['id'], 'name': o['name'], 'parent_id': o.get('parent_id')}
            for o in cfg['organizations'] if o['id'] in org_ids]
    return jsonify(orgs)


@app.route('/api/org/<org_id>/farms/list')
@auth_module.require_login
def org_farms_list(org_id):
    """Farms within this org's subtree — for org_admin dropdowns."""
    user = auth_module.get_current_user()
    if not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    farms = config_loader.get_farms_in_org_subtree(org_id)
    return jsonify([{'id': f['id'], 'name': f['name'], 'org_ids': f.get('org_ids', [])} for f in farms])


@app.route('/api/admin/orgs')
@auth_module.require_role('admin')
def admin_orgs():
    cfg = config_loader.load_config()
    result = []
    for org in cfg['organizations']:
        summary = config_loader.compute_org_summary(org['id'])
        user_count = sum(1 for u in cfg['users'] if u.get('org_id') == org['id'])
        result.append({
            'id': org['id'],
            'name': org['name'],
            'parent_id': org.get('parent_id'),
            'farm_count': summary['farm_count'],
            'avg_health': summary['avg_health'],
            'issues_count': summary['issues_count'],
            'last_report_date': summary['last_report_date'],
            'user_count': user_count,
        })
    return jsonify(result)


@app.route('/api/weather/<farm_id>')
def get_weather(farm_id):
    user = auth_module.get_current_user()
    if user and not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    lat = farm.get('lat')
    lng = farm.get('lng')
    if lat is None or lng is None:
        return jsonify({'error': 'No GPS coordinates configured for this farm'}), 400
    try:
        data = weather_module.fetch_weather(farm_id, lat, lng)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Weather fetch failed: {str(e)}'}), 502


@app.route('/api/farm/<farm_id>/farmers')
@auth_module.require_login
def get_farm_farmers(farm_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    farmers = config_loader.get_farmers_for_farm(farm_id)
    return jsonify(farmers)


@app.route('/api/admin/orgs', methods=['POST'])
@auth_module.require_role('admin')
def admin_create_org():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'name is required'}), 400
    parent_id = data.get('parent_id') or None
    try:
        org = config_loader.create_org(name=data['name'].strip(), parent_id=parent_id)
        return jsonify(org), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/farms', methods=['POST'])
@auth_module.require_login
def admin_create_farm():
    user = auth_module.get_current_user()
    if user['role'] not in ('admin', 'org_admin'):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'name is required'}), 400
    # Accept org_ids (list) or legacy org_id (scalar)
    org_ids = data.get('org_ids') or ([data['org_id']] if data.get('org_id') else [])
    if not org_ids:
        return jsonify({'error': 'at least one org_id is required'}), 400
    if user['role'] == 'org_admin':
        inaccessible = [oid for oid in org_ids if not auth_module.can_access_org(user, oid)]
        if inaccessible:
            return jsonify({'error': f'Forbidden: orgs outside your scope: {inaccessible}'}), 403
    try:
        lat = float(data['lat']) if data.get('lat') not in (None, '') else None
        lng = float(data['lng']) if data.get('lng') not in (None, '') else None
    except (ValueError, TypeError):
        return jsonify({'error': 'lat and lng must be numbers'}), 400
    try:
        farm = config_loader.create_farm(
            name=data['name'].strip(), org_ids=org_ids, lat=lat, lng=lng)
        return jsonify(farm), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/users', methods=['POST'])
@auth_module.require_role('admin')
def admin_create_user():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password') or not data.get('role'):
        return jsonify({'error': 'username, password and role are required'}), 400
    new_role = data['role']
    if new_role not in ('admin', 'org_admin', 'user'):
        return jsonify({'error': 'role must be admin, org_admin, or user'}), 400
    assigned_org = data.get('org_id') or None
    farm_ids = [f.strip() for f in data.get('farm_ids', []) if f.strip()]
    try:
        new_user = config_loader.create_user(
            username=data['username'].strip(), password=data['password'],
            role=new_role, display_name=data.get('display_name', '').strip() or None,
            org_id=assigned_org, farm_ids=farm_ids)
        return jsonify(new_user), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/farms/<farm_id>/upload', methods=['POST'])
@auth_module.require_login
def admin_upload_report(farm_id):
    user = auth_module.get_current_user()
    if user['role'] not in ('admin', 'org_admin'):
        return jsonify({'error': 'Forbidden'}), 403
    if user['role'] == 'org_admin' and not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden: farm is outside your scope'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.json'):
        return jsonify({'error': 'Only .json files are accepted'}), 400
    filename = secure_filename(f.filename)
    dest = os.path.join(farm['data_folder'], filename)
    if os.path.exists(dest):
        return jsonify({'error': f'File {filename} already exists for this farm'}), 409
    try:
        content = f.read()
        json.loads(content)
    except Exception:
        return jsonify({'error': 'File is not valid JSON'}), 400
    with open(dest, 'wb') as out:
        out.write(content)
    return jsonify({'ok': True, 'filename': filename, 'farm_id': farm_id}), 201


@app.route('/api/admin/users')
@auth_module.require_role('admin')
def admin_users():
    cfg = config_loader.load_config()
    result = []
    for user in cfg['users']:
        result.append({
            'id': user['id'],
            'username': user['username'],
            'display_name': user.get('display_name', user['username']),
            'role': user['role'],
            'org_id': user.get('org_id'),
            'farm_ids': user.get('farm_ids', []),
        })
    return jsonify(result)


@app.route('/api/admin/users/<user_id>', methods=['PATCH'])
@auth_module.require_role('admin')
def admin_update_user(user_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    display_name = data.get('display_name', '').strip() or None
    password = data.get('password', '').strip() or None
    try:
        updated = config_loader.update_user(user_id, display_name=display_name, password=password)
        return jsonify(updated)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404


# ---------------------------------------------------------------------------
# Static files + error handlers
# ---------------------------------------------------------------------------

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


@app.errorhandler(404)
def not_found(_error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(_error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
