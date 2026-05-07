import os
import json
import glob
import uuid

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from flask import Flask, jsonify, make_response, render_template, redirect, request, send_from_directory
from werkzeug.utils import secure_filename

import config_loader
import auth as auth_module
import cognito_auth
import weather as weather_module
import i18n
import session_state
import worker as worker_module

import threading as _threading

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

_UPLOADS_BASE = 'data/uploads'
_COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true').lower() != 'false'
_ALLOWED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tiff', '.tif', '.bmp'}
_FLUSH_INTERVAL_MINUTES = int(os.environ.get('FLUSH_INTERVAL_MINUTES', '5'))

# Start background worker on first request (thread-safe, works with Flask reloader)
_worker_started = False
_worker_lock = _threading.Lock()


@app.before_request
def _ensure_worker():
    global _worker_started
    if not _worker_started:
        with _worker_lock:
            if not _worker_started:
                worker_module.start_worker(flush_interval_minutes=_FLUSH_INTERVAL_MINUTES)
                _worker_started = True


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route('/api/me')
@auth_module.require_login
def api_me():
    user = auth_module.get_current_user()
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'display_name': user.get('display_name', user['username']),
        'role': user['role'],
        'org_id': user.get('org_id'),
        'farm_ids': user.get('farm_ids', []),
    })


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    tokens = cognito_auth.authenticate_user(data.get('username', ''), data.get('password', ''))
    if not tokens or not tokens.get('access_token'):
        return jsonify({'error': 'Invalid username or password'}), 401
    username = cognito_auth.get_username(tokens['access_token'])
    user = config_loader.get_user_by_username(username)
    if not user:
        return jsonify({'error': 'User not found'}), 401
    redirect_url = _redirect_for_user(user)
    resp = make_response(jsonify({
        'ok': True,
        'redirect_url': redirect_url,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'display_name': user.get('display_name', user['username']),
            'role': user['role'],
            'org_id': user.get('org_id'),
            'farm_ids': user.get('farm_ids', []),
        },
    }))
    resp.set_cookie('access_token', tokens['access_token'],
                    httponly=True, secure=_COOKIE_SECURE, samesite='Strict',
                    max_age=tokens['expires_in'])
    return resp


@app.route('/api/logout', methods=['POST'])
def api_logout():
    resp = make_response(jsonify({'ok': True}))
    resp.delete_cookie('access_token')
    return resp


@app.route('/api/set-lang', methods=['POST'])
def set_lang():
    data = request.get_json()
    lang = data.get('lang', 'en') if data else 'en'
    if lang not in i18n.SUPPORTED_LANGS:
        return jsonify({'error': 'Unsupported language'}), 400
    resp = make_response(jsonify({'ok': True, 'lang': lang}))
    resp.set_cookie('lang', lang, max_age=60 * 60 * 24 * 365,
                    httponly=False, samesite='Strict')
    return resp


def _redirect_for_user(user):
    if user['role'] == 'admin':
        return '/admin'
    elif user['role'] == 'org_admin':
        return f'/org/{user["org_id"]}'
    else:
        farms = config_loader.get_accessible_farms(user)
        if farms:
            org_ids = farms[0].get('org_ids', [])
            return f'/org/{org_ids[0]}' if org_ids else f'/farm/{farms[0]["id"]}'
        return '/'


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    user = auth_module.get_current_user()
    if user:
        return redirect(_redirect_for_user(user))
    return redirect('/login')


@app.route('/login')
def login_page():
    user = auth_module.get_current_user()
    if user:
        return redirect(_redirect_for_user(user))
    t = i18n.get_translations()
    lang = i18n.get_lang()
    return render_template('login.html', year=datetime.now().year, t=t, lang=lang,
                           supported_langs=i18n.SUPPORTED_LANGS)


@app.route('/admin')
def admin_dashboard():
    user = auth_module.get_current_user()
    if not user:
        return redirect('/login')
    if user['role'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    nav_context = config_loader.build_nav_context(user)
    cfg = config_loader.load_config()
    t = i18n.get_translations()
    lang = i18n.get_lang()
    return render_template('admin_dashboard.html', user=user, nav_context=nav_context,
                           page_title=t['admin_dashboard'], t=t, lang=lang,
                           supported_langs=i18n.SUPPORTED_LANGS,
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
    t = i18n.get_translations()
    lang = i18n.get_lang()
    return render_template('org_dashboard.html', user=user, nav_context=nav_context,
                           org=org, breadcrumb=breadcrumb, page_title=org['name'],
                           t=t, lang=lang, supported_langs=i18n.SUPPORTED_LANGS)


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
    t = i18n.get_translations()
    lang = i18n.get_lang()
    return render_template('farm_map.html', user=user, nav_context=nav_context,
                           farm=farm, breadcrumb=breadcrumb, page_title=farm['name'],
                           t=t, lang=lang, supported_langs=i18n.SUPPORTED_LANGS)


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


# ---------------------------------------------------------------------------
# Farm endpoints
# ---------------------------------------------------------------------------

@app.route('/api/farms')
@auth_module.require_login
def list_farms():
    user = auth_module.get_current_user()
    farms = config_loader.get_accessible_farms(user)
    return jsonify([
        {'id': f['id'], 'name': f['name'], 'org_ids': f.get('org_ids', []),
         'lat': f.get('lat'), 'lng': f.get('lng')}
        for f in farms
    ])


@app.route('/api/farm/<farm_id>')
@auth_module.require_login
def get_farm_detail(farm_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    return jsonify({
        'id': farm['id'], 'name': farm['name'],
        'org_ids': farm.get('org_ids', []),
        'lat': farm.get('lat'), 'lng': farm.get('lng'),
    })


@app.route('/api/farm/<farm_id>/summary')
@auth_module.require_login
def get_farm_summary(farm_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    return jsonify(config_loader.compute_farm_summary(farm))


@app.route('/api/farm/<farm_id>/farmers')
@auth_module.require_login
def get_farm_farmers(farm_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    return jsonify(config_loader.get_farmers_for_farm(farm_id))


@app.route('/api/files')
@auth_module.require_login
def get_files():
    farm_id = request.args.get('farm_id')
    if not farm_id:
        return jsonify({'error': 'farm_id parameter required'}), 400
    user = auth_module.get_current_user()
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    data_files = glob.glob(os.path.join(farm['data_folder'], '*.json'))
    files = []
    for f in sorted(data_files, reverse=True):
        filename = os.path.basename(f)
        files.append({'filename': filename, 'display': filename.replace('.json', '').replace('_', ' ')})
    return jsonify(files)


@app.route('/api/data/<farm_id>/<filename>')
@auth_module.require_login
def get_data(farm_id, filename):
    user = auth_module.get_current_user()
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    if '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    filepath = os.path.join(farm['data_folder'], filename)
    try:
        with open(filepath, 'r') as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({'error': 'Data file not found'}), 404
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON data'}), 500


@app.route('/api/weather/<farm_id>')
@auth_module.require_login
def get_weather(farm_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_farm(user, farm_id):
        return jsonify({'error': 'Forbidden'}), 403
    farm = config_loader.get_farm(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    lat, lng = farm.get('lat'), farm.get('lng')
    if lat is None or lng is None:
        return jsonify({'error': 'No GPS coordinates configured for this farm'}), 400
    try:
        return jsonify(weather_module.fetch_weather(farm_id, lat, lng))
    except Exception as e:
        return jsonify({'error': f'Weather fetch failed: {str(e)}'}), 502


# ---------------------------------------------------------------------------
# Organization endpoints
# ---------------------------------------------------------------------------

@app.route('/api/orgs')
@auth_module.require_login
def list_orgs():
    user = auth_module.get_current_user()
    orgs = config_loader.get_accessible_orgs(user)
    return jsonify([
        {'id': o['id'], 'name': o['name'], 'parent_id': o.get('parent_id'),
         'children': o.get('children', []), 'farms': o.get('farms', [])}
        for o in orgs
    ])


@app.route('/api/org/<org_id>/detail')
@auth_module.require_login
def get_org_detail(org_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    org = config_loader.get_org(org_id)
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    return jsonify({
        'id': org['id'], 'name': org['name'],
        'parent_id': org.get('parent_id'),
        'children': org.get('children', []),
        'farms': org.get('farms', []),
    })


@app.route('/api/org/<org_id>/summary')
@auth_module.require_login
def org_summary(org_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    org = config_loader.get_org(org_id)
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    summary = config_loader.compute_org_summary(org_id)
    if user['role'] == 'user':
        accessible_ids = {f['id'] for f in config_loader.get_accessible_farms(user)}
        summary['farms'] = [f for f in summary['farms'] if f['farm_id'] in accessible_ids]
        summary['farm_count'] = len(summary['farms'])
    return jsonify(summary)


@app.route('/api/org/<org_id>/orgs/list')
@auth_module.require_login
def org_orgs_list(org_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    org_ids = config_loader.get_org_subtree_ids(org_id)
    cfg = config_loader.load_config()
    return jsonify([
        {'id': o['id'], 'name': o['name'], 'parent_id': o.get('parent_id')}
        for o in cfg['organizations'] if o['id'] in org_ids
    ])


@app.route('/api/org/<org_id>/farms/list')
@auth_module.require_login
def org_farms_list(org_id):
    user = auth_module.get_current_user()
    if not auth_module.can_access_org(user, org_id):
        return jsonify({'error': 'Forbidden'}), 403
    farms = config_loader.get_farms_in_org_subtree(org_id)
    return jsonify([{'id': f['id'], 'name': f['name'], 'org_ids': f.get('org_ids', [])} for f in farms])


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@app.route('/api/admin/orgs')
@auth_module.require_role('admin')
def admin_orgs():
    cfg = config_loader.load_config()
    result = []
    for org in cfg['organizations']:
        summary = config_loader.compute_org_summary(org['id'])
        user_count = sum(1 for u in cfg['users'] if u.get('org_id') == org['id'])
        result.append({
            'id': org['id'], 'name': org['name'], 'parent_id': org.get('parent_id'),
            'farm_count': summary['farm_count'], 'avg_health': summary['avg_health'],
            'issues_count': summary['issues_count'], 'last_report_date': summary['last_report_date'],
            'user_count': user_count,
        })
    return jsonify(result)


@app.route('/api/admin/orgs', methods=['POST'])
@auth_module.require_role('admin')
def admin_create_org():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'name is required'}), 400
    try:
        org = config_loader.create_org(name=data['name'].strip(), parent_id=data.get('parent_id') or None)
        return jsonify(org), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/orgs/list')
@auth_module.require_role('admin')
def admin_orgs_list():
    cfg = config_loader.load_config()
    return jsonify([{'id': o['id'], 'name': o['name'], 'parent_id': o.get('parent_id')}
                    for o in cfg['organizations']])


@app.route('/api/admin/farms', methods=['POST'])
@auth_module.require_login
def admin_create_farm():
    user = auth_module.get_current_user()
    if user['role'] not in ('admin', 'org_admin'):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'name is required'}), 400
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
        farm = config_loader.create_farm(name=data['name'].strip(), org_ids=org_ids, lat=lat, lng=lng)
        return jsonify(farm), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/farms/list')
@auth_module.require_role('admin')
def admin_farms_list():
    cfg = config_loader.load_config()
    return jsonify([{'id': f['id'], 'name': f['name'], 'org_ids': f.get('org_ids', [])}
                    for f in cfg['farms']])


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
    return jsonify([{
        'id': u['id'], 'username': u['username'],
        'display_name': u.get('display_name', u['username']),
        'role': u['role'], 'org_id': u.get('org_id'), 'farm_ids': u.get('farm_ids', []),
    } for u in cfg['users']])


@app.route('/api/admin/users', methods=['POST'])
@auth_module.require_role('admin')
def admin_create_user():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password') or not data.get('role'):
        return jsonify({'error': 'username, password and role are required'}), 400
    new_role = data['role']
    if new_role not in ('admin', 'org_admin', 'user'):
        return jsonify({'error': 'role must be admin, org_admin, or user'}), 400
    farm_ids = [f.strip() for f in data.get('farm_ids', []) if f.strip()]
    try:
        new_user = config_loader.create_user(
            username=data['username'].strip(), password=data['password'],
            role=new_role, display_name=data.get('display_name', '').strip() or None,
            org_id=data.get('org_id') or None, farm_ids=farm_ids)
        return jsonify(new_user), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/users/<user_id>', methods=['PATCH'])
@auth_module.require_role('admin')
def admin_update_user(user_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    try:
        updated = config_loader.update_user(
            user_id,
            display_name=data.get('display_name', '').strip() or None,
            password=data.get('password', '').strip() or None)
        return jsonify(updated)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404


# ---------------------------------------------------------------------------
# Image upload with GPS
# ---------------------------------------------------------------------------

@app.route('/api/upload/<session_id>', methods=['POST'])
@auth_module.require_login
def upload_image(session_id):
    try:
        uuid.UUID(session_id)
    except ValueError:
        return jsonify({'error': 'Invalid session_id: must be a UUID'}), 400

    try:
        lat = float(request.form['lat'])
        lng = float(request.form['lng'])
    except (KeyError, ValueError, TypeError):
        return jsonify({'error': 'lat and lng are required and must be numbers'}), 400

    alt_raw = request.form.get('alt')
    try:
        alt = float(alt_raw) if alt_raw not in (None, '') else None
    except (ValueError, TypeError):
        return jsonify({'error': 'alt must be a number if provided'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'File has no name'}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        return jsonify({'error': f'Unsupported file type. Allowed: {", ".join(sorted(_ALLOWED_IMAGE_EXTS))}'}), 400

    session_dir = os.path.join(_UPLOADS_BASE, session_id)
    os.makedirs(session_dir, exist_ok=True)

    now = datetime.utcnow()
    filename = f'{now.strftime("%Y%m%d_%H%M%S_%f")}_{secure_filename(f.filename) or f"image{ext}"}'
    f.save(os.path.join(session_dir, filename))

    entry = {'image_filename': filename, 'latitude': lat, 'longitude': lng,
             'altitude': alt, 'timestamp': now.isoformat()}
    with open(os.path.join(session_dir, 'gps.jsonl'), 'a') as jf:
        jf.write(json.dumps(entry) + '\n')

    batch = session_state.add_image(session_id, filename)
    if batch:
        batch_index, image_paths = batch
        worker_module.batch_queue.put((session_id, batch_index, image_paths))

    return jsonify({
        'ok': True, 'session_id': session_id, 'image_filename': filename,
        'gps': {'latitude': lat, 'longitude': lng, 'altitude': alt},
        'batch_queued': batch is not None,
    }), 201


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(_error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
