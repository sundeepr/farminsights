import json
import os
import glob

_config_cache = None

def load_config():
    global _config_cache
    if _config_cache is None:
        with open('data/config.json', 'r') as f:
            _config_cache = json.load(f)
    return _config_cache

def reload_config():
    global _config_cache
    _config_cache = None
    return load_config()

def save_config(config):
    """Write config back to disk and invalidate cache."""
    global _config_cache
    with open('data/config.json', 'w') as f:
        json.dump(config, f, indent=2)
    _config_cache = config

def _next_id(prefix, items):
    """Generate next sequential ID like org_008, farm_007, u10."""
    nums = []
    for item in items:
        try:
            nums.append(int(item['id'].replace(prefix, '').lstrip('_')))
        except (ValueError, AttributeError):
            pass
    return f"{prefix}{(max(nums) + 1) if nums else 1:03d}"

def create_org(name, parent_id=None):
    """Add a new org to config. Updates parent's children list. Returns new org."""
    config = load_config()
    new_id = _next_id('org_', config['organizations'])
    new_org = {'id': new_id, 'name': name, 'parent_id': parent_id, 'children': [], 'farms': []}
    config['organizations'].append(new_org)
    if parent_id:
        for org in config['organizations']:
            if org['id'] == parent_id:
                org['children'].append(new_id)
                break
    save_config(config)
    return new_org

def create_farm(name, org_ids, lat=None, lng=None):
    """Add a new farm to config. Creates data folder. org_ids is a list. Returns new farm."""
    if isinstance(org_ids, str):
        org_ids = [org_ids]
    config = load_config()
    new_id = _next_id('farm_', config['farms'])
    data_folder = f'data/{new_id}'
    os.makedirs(data_folder, exist_ok=True)
    new_farm = {'id': new_id, 'name': name, 'org_ids': org_ids, 'data_folder': data_folder}
    if lat is not None:
        new_farm['lat'] = lat
    if lng is not None:
        new_farm['lng'] = lng
    config['farms'].append(new_farm)
    for org in config['organizations']:
        if org['id'] in org_ids and new_id not in org.get('farms', []):
            org['farms'].append(new_id)
    save_config(config)
    return new_farm

def get_farmers_for_farm(farm_id):
    """Return list of users (without passwords) who have this farm in their farm_ids."""
    config = load_config()
    result = []
    for user in config['users']:
        if farm_id in user.get('farm_ids', []):
            result.append({k: v for k, v in user.items() if k != 'password'})
    return result

def create_user(username, password, role, display_name=None, org_id=None, farm_ids=None):
    """Add a new user to config. Returns new user (without password)."""
    config = load_config()
    # Check username uniqueness
    if any(u['username'].lower() == username.lower() for u in config['users']):
        raise ValueError(f"Username '{username}' already exists")
    nums = []
    for u in config['users']:
        try:
            nums.append(int(u['id'].lstrip('u')))
        except ValueError:
            pass
    new_num = (max(nums) + 1) if nums else 1
    new_id = f'u{new_num}'
    new_user = {
        'id': new_id,
        'username': username,
        'display_name': display_name or username,
        'password': password,
        'role': role,
        'org_id': org_id,
        'farm_ids': farm_ids or [],
    }
    config['users'].append(new_user)
    save_config(config)
    return {k: v for k, v in new_user.items() if k != 'password'}

def update_user(user_id, display_name=None, password=None):
    """Update a user's display_name and/or password. Returns updated user (without password)."""
    config = load_config()
    for user in config['users']:
        if user['id'] == user_id:
            if display_name is not None:
                user['display_name'] = display_name
            if password:
                user['password'] = password
            save_config(config)
            return {k: v for k, v in user.items() if k != 'password'}
    raise ValueError(f"User '{user_id}' not found")

def get_user_by_email(email):
    config = load_config()
    for user in config['users']:
        if user.get('email', '').lower() == email.lower():
            return user
    return None

def get_user_by_username(username):
    config = load_config()
    for user in config['users']:
        if user['username'].lower() == username.lower():
            return user
    return None

def get_user_by_credentials(username, password):
    config = load_config()
    for user in config['users']:
        if user['username'] == username and user['password'] == password:
            return user
    return None

def get_user_by_id(user_id):
    config = load_config()
    for user in config['users']:
        if user['id'] == user_id:
            return user
    return None

def get_farm(farm_id):
    config = load_config()
    for farm in config['farms']:
        if farm['id'] == farm_id:
            return farm
    return None

def get_org(org_id):
    config = load_config()
    for org in config['organizations']:
        if org['id'] == org_id:
            return org
    return None

def get_org_subtree_ids(org_id):
    """Return org_id plus all descendant org IDs (recursive)."""
    config = load_config()
    org_map = {o['id']: o for o in config['organizations']}
    result = []
    stack = [org_id]
    while stack:
        current = stack.pop()
        result.append(current)
        org = org_map.get(current)
        if org:
            stack.extend(org.get('children', []))
    return result

def get_farms_in_org_subtree(org_id):
    """Return all farm dicts in org_id and all descendant orgs."""
    config = load_config()
    org_ids = get_org_subtree_ids(org_id)
    farm_map = {f['id']: f for f in config['farms']}
    org_map = {o['id']: o for o in config['organizations']}
    result = []
    seen = set()
    for oid in org_ids:
        org = org_map.get(oid)
        if org:
            for fid in org.get('farms', []):
                if fid not in seen:
                    farm = farm_map.get(fid)
                    if farm:
                        result.append(farm)
                        seen.add(fid)
    return result

def get_accessible_farms(user):
    """Return list of farm dicts accessible to the user based on their role."""
    config = load_config()
    if user['role'] == 'admin':
        return list(config['farms'])
    elif user['role'] == 'org_admin':
        return get_farms_in_org_subtree(user['org_id'])
    else:
        farm_map = {f['id']: f for f in config['farms']}
        return [farm_map[fid] for fid in user.get('farm_ids', []) if fid in farm_map]

def get_accessible_orgs(user):
    """Return list of org dicts accessible to the user."""
    config = load_config()
    if user['role'] == 'admin':
        return list(config['organizations'])
    elif user['role'] == 'org_admin':
        org_ids = get_org_subtree_ids(user['org_id'])
        org_map = {o['id']: o for o in config['organizations']}
        return [org_map[oid] for oid in org_ids if oid in org_map]
    else:
        # Normal users: return orgs that contain their farms
        accessible_farm_ids = set(user.get('farm_ids', []))
        result = []
        seen = set()
        for org in config['organizations']:
            if any(fid in accessible_farm_ids for fid in org.get('farms', [])):
                if org['id'] not in seen:
                    result.append(org)
                    seen.add(org['id'])
        return result

def build_org_tree(org_id):
    """Build a nested dict tree for sidebar rendering."""
    config = load_config()
    org_map = {o['id']: o for o in config['organizations']}
    farm_map = {f['id']: f for f in config['farms']}

    def _build(oid):
        org = org_map.get(oid)
        if not org:
            return None
        return {
            'id': org['id'],
            'name': org['name'],
            'children': [_build(cid) for cid in org.get('children', []) if _build(cid)],
            'farms': [farm_map[fid] for fid in org.get('farms', []) if fid in farm_map],
        }

    return _build(org_id)

def get_org_ancestry(org_id):
    """Return ordered list [root_org, ..., org_id] for breadcrumbs."""
    config = load_config()
    org_map = {o['id']: o for o in config['organizations']}
    chain = []
    current = org_id
    visited = set()
    while current and current not in visited:
        org = org_map.get(current)
        if not org:
            break
        chain.append(org)
        visited.add(current)
        current = org.get('parent_id')
    chain.reverse()
    return chain

def build_nav_context(user, current_org_id=None, current_farm_id=None):
    """Build the nav_context dict passed to every template."""
    config = load_config()

    if user['role'] == 'admin':
        dashboard_url = '/admin'
    elif user['role'] == 'org_admin':
        dashboard_url = f'/org/{user["org_id"]}'
    else:
        farms = get_accessible_farms(user)
        if farms:
            org_ids = farms[0].get('org_ids', [])
            dashboard_url = f'/org/{org_ids[0]}' if org_ids else f'/farm/{farms[0]["id"]}'
        else:
            dashboard_url = '/'

    ctx = {
        'user': user,
        'current_org_id': current_org_id,
        'current_farm_id': current_farm_id,
        'orgs_tree': None,
        'user_farms': [],
        'all_orgs': [],
        'dashboard_url': dashboard_url,
    }

    if user['role'] == 'admin':
        ctx['all_orgs'] = [o for o in config['organizations'] if o['parent_id'] is None]
    elif user['role'] == 'org_admin':
        ctx['orgs_tree'] = build_org_tree(user['org_id'])
    else:
        ctx['user_farms'] = get_accessible_farms(user)

    return ctx

def compute_farm_summary(farm):
    """Read most recent session JSON for a farm and compute health metrics."""
    folder = farm['data_folder']
    files = sorted(glob.glob(os.path.join(folder, '*.json')), reverse=True)
    if not files:
        return {
            'farm_id': farm['id'],
            'farm_name': farm['name'],
            'avg_health': None,
            'issues_count': 0,
            'total_images': 0,
            'last_report_date': None,
            'status': 'no_data',
        }

    latest = files[0]
    try:
        with open(latest, 'r') as f:
            data = json.load(f)
    except Exception:
        return {
            'farm_id': farm['id'],
            'farm_name': farm['name'],
            'avg_health': None,
            'issues_count': 0,
            'total_images': 0,
            'last_report_date': None,
            'status': 'error',
        }

    images = data.get('images', [])
    scores = [
        img['plant_health_analysis']['health_score']
        for img in images
        if img.get('plant_health_analysis') and img['plant_health_analysis'].get('health_score') is not None
    ]
    avg_health = round(sum(scores) / len(scores), 1) if scores else None
    issues_count = sum(1 for s in scores if s < 65)

    metadata = data.get('report_metadata', {})
    last_report_date = metadata.get('generated_at', os.path.basename(latest))

    if avg_health is None:
        status = 'unknown'
    elif avg_health >= 75:
        status = 'good'
    elif avg_health >= 65:
        status = 'fair'
    else:
        status = 'poor'

    return {
        'farm_id': farm['id'],
        'farm_name': farm['name'],
        'avg_health': avg_health,
        'issues_count': issues_count,
        'total_images': len(images),
        'last_report_date': last_report_date,
        'status': status,
        'file_count': len(files),
    }

def compute_org_summary(org_id):
    """Aggregate farm summaries for an org and all its descendants."""
    farms = get_farms_in_org_subtree(org_id)
    farm_summaries = [compute_farm_summary(f) for f in farms]

    health_vals = [s['avg_health'] for s in farm_summaries if s['avg_health'] is not None]
    avg_health = round(sum(health_vals) / len(health_vals), 1) if health_vals else None
    issues_count = sum(s['issues_count'] for s in farm_summaries)
    total_images = sum(s['total_images'] for s in farm_summaries)

    dates = [s['last_report_date'] for s in farm_summaries if s['last_report_date']]
    last_report_date = max(dates) if dates else None

    config = load_config()
    org = get_org(org_id)
    child_summaries = []
    for cid in org.get('children', []):
        child_org = get_org(cid)
        if child_org:
            child_summaries.append(compute_org_summary(cid))

    return {
        'org_id': org_id,
        'org_name': org['name'] if org else org_id,
        'farm_count': len(farms),
        'avg_health': avg_health,
        'issues_count': issues_count,
        'total_images': total_images,
        'last_report_date': last_report_date,
        'farms': farm_summaries,
        'children': child_summaries,
    }
