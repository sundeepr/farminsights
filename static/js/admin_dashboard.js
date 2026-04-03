/**
 * admin_dashboard.js — Admin dashboard: tables, create org/farm/user, upload report
 */

let _allOrgs = [];
let _allFarms = [];
let _t = {};

document.addEventListener('DOMContentLoaded', () => {
    _t = window._t || {};
    loadAdminData();
    setupDragDrop();
});

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadAdminData() {
    const [orgsRes, usersRes, orgsListRes, farmsListRes] = await Promise.all([
        fetch('/api/admin/orgs'),
        fetch('/api/admin/users'),
        fetch('/api/admin/orgs/list'),
        fetch('/api/admin/farms/list'),
    ]);

    if (orgsListRes.ok) _allOrgs = await orgsListRes.json();
    if (farmsListRes.ok) _allFarms = await farmsListRes.json();

    if (orgsRes.ok) {
        const orgs = await orgsRes.json();
        renderOrgs(orgs);
        computeSystemHealth(orgs);
    }

    if (usersRes.ok) {
        const users = await usersRes.json();
        renderUsers(users);
    }

    renderFarmsTable();
}

// ---------------------------------------------------------------------------
// Table renderers
// ---------------------------------------------------------------------------

function renderOrgs(orgs) {
    const orgMap = Object.fromEntries(_allOrgs.map(o => [o.id, o.name]));
    const tbody = document.getElementById('orgsBody');
    if (!orgs.length) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#adb5bd;padding:30px;">${_t.no_organizations || 'No organizations found.'}</td></tr>`;
        return;
    }
    tbody.innerHTML = '';
    orgs.forEach(org => {
        const health = org.avg_health;
        const statusClass = health !== null ? getStatusClass(health) : 'unknown';
        const parentName = org.parent_id ? (orgMap[org.parent_id] || org.parent_id) : '—';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escHtml(org.name)}</strong></td>
            <td style="color:#6c757d">${escHtml(parentName)}</td>
            <td>${org.farm_count}</td>
            <td>${org.user_count}</td>
            <td>${health !== null
                ? `<span class="metric-value ${statusClass}" style="font-size:1em;">${health}</span>`
                : '<span style="color:#adb5bd">—</span>'
            }</td>
            <td>${org.issues_count > 0
                ? `<span class="badge badge-poor">${org.issues_count}</span>`
                : `<span style="color:#adb5bd">0</span>`
            }</td>
            <td>${formatDate(org.last_report_date)}</td>
            <td><a href="/org/${escHtml(org.id)}" class="btn-action">${_t.view || 'View'}</a></td>
        `;
        tbody.appendChild(tr);
    });
}

async function renderFarmsTable() {
    const orgMap = Object.fromEntries(_allOrgs.map(o => [o.id, o.name]));
    const tbody = document.getElementById('farmsBody');
    if (!_allFarms.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#adb5bd;padding:30px;">${_t.no_farms_in_org || 'No farms found.'}</td></tr>`;
        return;
    }
    tbody.innerHTML = '';
    for (const farm of _allFarms) {
        const orgNames = (farm.org_ids || []).map(id => escHtml(orgMap[id] || id)).join(', ') || '—';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escHtml(farm.name)}</strong></td>
            <td style="color:#6c757d">${orgNames}</td>
            <td id="fh-${escHtml(farm.id)}"><span style="color:#adb5bd">—</span></td>
            <td id="fs-${escHtml(farm.id)}"><span style="color:#adb5bd">—</span></td>
            <td id="fc-${escHtml(farm.id)}"><span style="color:#adb5bd">—</span></td>
            <td id="fd-${escHtml(farm.id)}"><span style="color:#adb5bd">—</span></td>
            <td>
                <div style="display:flex;gap:6px;justify-content:center;">
                    <a href="/farm/${escHtml(farm.id)}" class="btn-action">${_t.view || 'View'}</a>
                    <button class="btn-action" style="background:linear-gradient(135deg,#1565c0,#1976d2);"
                        onclick="openUploadForFarm('${escHtml(farm.id)}')">${_t.upload_short || '↑ Upload'}</button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
        fetchFarmSummary(farm.id);
    }
}

async function fetchFarmSummary(farmId) {
    try {
        const res = await fetch(`/api/files?farm_id=${farmId}`);
        if (!res.ok) return;
        const files = await res.json();
        document.getElementById(`fc-${farmId}`).textContent = files.length || 0;
        if (!files.length) return;
        // Load most recent file summary
        const dataRes = await fetch(`/api/data/${farmId}/${files[0].filename}`);
        if (!dataRes.ok) return;
        const data = await dataRes.json();
        const images = data.images || [];
        const scores = images
            .map(i => i.plant_health_analysis?.health_score)
            .filter(s => s !== null && s !== undefined);
        const avg = scores.length ? (scores.reduce((a,b) => a+b,0)/scores.length).toFixed(1) : null;
        const cls = avg !== null ? getStatusClass(parseFloat(avg)) : 'unknown';
        const status = avg === null ? (_t.no_data || 'no data') : parseFloat(avg) >= 75 ? (_t.good || 'good') : parseFloat(avg) >= 65 ? (_t.fair || 'fair') : (_t.poor || 'poor');
        if (avg !== null) {
            document.getElementById(`fh-${farmId}`).innerHTML =
                `<span class="metric-value ${cls}" style="font-size:1em;">${avg}</span>`;
            document.getElementById(`fs-${farmId}`).innerHTML =
                `<span class="badge badge-${cls}">${status}</span>`;
        }
        const meta = data.report_metadata;
        if (meta?.generated_at) {
            document.getElementById(`fd-${farmId}`).textContent = formatDate(meta.generated_at);
        }
    } catch { /* silently ignore */ }
}

function renderUsers(users) {
    const orgMap = Object.fromEntries(_allOrgs.map(o => [o.id, o.name]));
    const farmMap = Object.fromEntries(_allFarms.map(f => [f.id, f.name]));
    const tbody = document.getElementById('usersBody');
    if (!users.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#adb5bd;padding:30px;">${_t.no_users || 'No users found.'}</td></tr>`;
        return;
    }
    tbody.innerHTML = '';
    users.forEach(user => {
        const farmNames = (user.farm_ids || []).map(id => escHtml(farmMap[id] || id));
        const farmList = farmNames.length ? farmNames.join(', ') : '<span style="color:#adb5bd">—</span>';
        const orgName = user.org_id ? (orgMap[user.org_id] || user.org_id) : '—';
        const displayName = user.display_name || user.username;
        const userData = JSON.stringify({id: user.id, username: user.username, display_name: displayName}).replace(/"/g, '&quot;');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escHtml(displayName)}</strong></td>
            <td style="color:#6c757d">${escHtml(user.username)}</td>
            <td><span class="badge badge-${escHtml(user.role)}">${escHtml(user.role).replace('_', ' ')}</span></td>
            <td style="color:#6c757d">${escHtml(orgName)}</td>
            <td>${farmList}</td>
            <td><button class="btn-action" style="font-size:0.8em;padding:4px 10px;" onclick='openEditUserModal(${userData})'>${_t.edit || 'Edit'}</button></td>
        `;
        tbody.appendChild(tr);
    });
}

let _editingUserId = null;

function openEditUserModal(user) {
    _editingUserId = user.id;
    document.getElementById('editUserUsername').value = user.username;
    document.getElementById('editUserDisplayName').value = user.display_name || '';
    document.getElementById('editUserPassword').value = '';
    const err = document.getElementById('editUserModalError');
    err.style.display = 'none';
    document.getElementById('editUserModal').style.display = 'flex';
}

async function submitEditUser() {
    const displayName = document.getElementById('editUserDisplayName').value.trim();
    const password = document.getElementById('editUserPassword').value;
    if (!displayName) { setModalError('editUser', _t.display_name_required || 'Display name is required.'); return; }

    const btn = document.getElementById('editUserSubmitBtn');
    btn.disabled = true; btn.textContent = _t.saving || 'Saving…';
    try {
        const res = await fetch(`/api/admin/users/${_editingUserId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: displayName, password: password || null }),
        });
        const data = await res.json();
        if (!res.ok) { setModalError('editUser', data.error || 'Failed to update user.'); return; }
        closeModal('editUserModal');
        showToast(_t.user_updated || 'User updated');
        loadAdminData();
    } finally {
        btn.disabled = false; btn.textContent = _t.save_changes || 'Save Changes';
    }
}

function computeSystemHealth(orgs) {
    const scores = orgs.map(o => o.avg_health).filter(h => h !== null);
    const sysEl = document.getElementById('sysHealth');
    const subEl = document.getElementById('sysHealthSub');
    if (!scores.length) {
        sysEl.textContent = _t.na || 'N/A';
        subEl.textContent = _t.no_data_available || 'No data available';
        return;
    }
    const avg = (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1);
    const cls = getStatusClass(parseFloat(avg));
    sysEl.innerHTML = `<span class="${cls}">${avg}</span>`;
    subEl.textContent = (_t.across_orgs_count || 'Across {n} org(s)').replace('{n}', scores.length);
}

// ---------------------------------------------------------------------------
// Modal helpers
// ---------------------------------------------------------------------------

function openModal(id) {
    if (id === 'orgModal') populateOrgParentDropdown();
    if (id === 'farmModal') populateFarmOrgCheckboxes();
    if (id === 'userModal') populateUserDropdowns();
    if (id === 'uploadModal') populateUploadFarmDropdown();
    document.getElementById(id).style.display = 'flex';
}

function closeModal(id) {
    document.getElementById(id).style.display = 'none';
    // Clear errors and reset forms
    const errEl = document.getElementById(id.replace('Modal','') + 'ModalError') ||
                  document.getElementById('uploadModalError');
    if (errEl) errEl.style.display = 'none';
}

// Close modal when clicking overlay background
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('admin-modal-overlay')) {
        e.target.style.display = 'none';
    }
});

function setModalError(prefix, msg) {
    const el = document.getElementById(`${prefix}ModalError`);
    if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function clearModalError(prefix) {
    const el = document.getElementById(`${prefix}ModalError`);
    if (el) el.style.display = 'none';
}

// ---------------------------------------------------------------------------
// Dropdown populators
// ---------------------------------------------------------------------------

function populateOrgParentDropdown() {
    const sel = document.getElementById('orgParent');
    sel.innerHTML = `<option value="">${_t.none_top_level || '\u2014 None (top-level) \u2014'}</option>`;
    _allOrgs.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.id;
        opt.textContent = o.name;
        sel.appendChild(opt);
    });
}

function populateFarmOrgCheckboxes() {
    const container = document.getElementById('farmOrgCheckboxes');
    container.innerHTML = '';
    _allOrgs.forEach(o => {
        const label = document.createElement('label');
        label.innerHTML = `<input type="checkbox" value="${escHtml(o.id)}"> ${escHtml(o.name)}`;
        container.appendChild(label);
    });
}

function populateUserDropdowns() {
    const orgSel = document.getElementById('userOrg');
    orgSel.innerHTML = `<option value="">${_t.select_org || '\u2014 Select organization \u2014'}</option>`;
    _allOrgs.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.id;
        opt.textContent = o.name;
        orgSel.appendChild(opt);
    });

    const container = document.getElementById('farmCheckboxes');
    container.innerHTML = '';
    _allFarms.forEach(f => {
        const label = document.createElement('label');
        label.innerHTML = `<input type="checkbox" value="${escHtml(f.id)}"> ${escHtml(f.name)}`;
        container.appendChild(label);
    });
}

function populateUploadFarmDropdown() {
    const sel = document.getElementById('uploadFarm');
    sel.innerHTML = `<option value="">${_t.select_farm || '\u2014 Select farm \u2014'}</option>`;
    _allFarms.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.id;
        opt.textContent = f.name;
        sel.appendChild(opt);
    });
    // Reset file picker
    document.getElementById('reportFile').value = '';
    document.getElementById('fileDropText').innerHTML =
        `${_t.click_to_choose || 'Click to choose a .json file'}<br><span style="font-size:0.8em;color:#adb5bd;">${_t.or_drag_drop || 'or drag and drop here'}</span>`;
    document.getElementById('dropZone').classList.remove('has-file');
}

function openUploadForFarm(farmId) {
    openModal('uploadModal');
    document.getElementById('uploadFarm').value = farmId;
}

// Role change shows/hides org vs farms fields
function onRoleChange() {
    const role = document.getElementById('userRole').value;
    document.getElementById('userOrgGroup').style.display = role === 'org_admin' ? 'block' : 'none';
    document.getElementById('userFarmsGroup').style.display = role === 'user' ? 'block' : 'none';
}

// ---------------------------------------------------------------------------
// Submit handlers
// ---------------------------------------------------------------------------

async function submitCreateOrg() {
    clearModalError('org');
    const name = document.getElementById('orgName').value.trim();
    const parentId = document.getElementById('orgParent').value;
    if (!name) { setModalError('org', _t.org_name_required || 'Organization name is required.'); return; }

    const btn = document.querySelector('#orgModal .admin-btn-submit');
    btn.disabled = true; btn.textContent = _t.creating || 'Creating…';

    try {
        const res = await fetch('/api/admin/orgs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, parent_id: parentId || null }),
        });
        const data = await res.json();
        if (!res.ok) { setModalError('org', data.error || 'Failed to create organization.'); return; }
        closeModal('orgModal');
        document.getElementById('orgName').value = '';
        showToast((_t.org_created || 'Organization "{name}" created').replace('{name}', name));
        await refreshDropdowns();
        loadAdminData();
    } finally {
        btn.disabled = false; btn.textContent = _t.create_organization || 'Create Organization';
    }
}

async function submitCreateFarm() {
    clearModalError('farm');
    const name = document.getElementById('farmName').value.trim();
    const orgIds = [...document.querySelectorAll('#farmOrgCheckboxes input:checked')].map(el => el.value);
    const lat = document.getElementById('farmLat').value;
    const lng = document.getElementById('farmLng').value;
    if (!name) { setModalError('farm', _t.farm_name_required || 'Farm name is required.'); return; }
    if (!orgIds.length) { setModalError('farm', _t.select_at_least_one_org || 'Please select at least one organization.'); return; }

    const btn = document.querySelector('#farmModal .admin-btn-submit');
    btn.disabled = true; btn.textContent = _t.creating || 'Creating…';

    try {
        const res = await fetch('/api/admin/farms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, org_ids: orgIds, lat: lat || null, lng: lng || null }),
        });
        const data = await res.json();
        if (!res.ok) { setModalError('farm', data.error || 'Failed to create farm.'); return; }
        closeModal('farmModal');
        document.getElementById('farmName').value = '';
        document.getElementById('farmLat').value = '';
        document.getElementById('farmLng').value = '';
        showToast((_t.farm_created || 'Farm "{name}" created').replace('{name}', name));
        await refreshDropdowns();
        loadAdminData();
    } finally {
        btn.disabled = false; btn.textContent = _t.create_farm || 'Create Farm';
    }
}

async function submitCreateUser() {
    clearModalError('user');
    const displayName = document.getElementById('userDisplayName').value.trim();
    const username = document.getElementById('userName').value.trim();
    const password = document.getElementById('userPassword').value;
    const role = document.getElementById('userRole').value;
    const orgId = document.getElementById('userOrg').value;
    const farmIds = [...document.querySelectorAll('#farmCheckboxes input:checked')].map(el => el.value);

    if (!displayName) { setModalError('user', _t.display_name_required || 'Display name is required.'); return; }
    if (!username) { setModalError('user', _t.username_required || 'Username is required.'); return; }
    if (!password) { setModalError('user', _t.password_required || 'Password is required.'); return; }
    if (!role) { setModalError('user', _t.select_role_error || 'Please select a role.'); return; }
    if (role === 'org_admin' && !orgId) { setModalError('user', _t.select_org_for_admin || 'Please select an organization for this Org Admin.'); return; }

    const btn = document.querySelector('#userModal .admin-btn-submit');
    btn.disabled = true; btn.textContent = _t.creating || 'Creating…';

    try {
        const res = await fetch('/api/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                display_name: displayName, username, password, role,
                org_id: (role === 'org_admin' ? orgId : null) || null,
                farm_ids: role === 'user' ? farmIds : [],
            }),
        });
        const data = await res.json();
        if (!res.ok) { setModalError('user', data.error || 'Failed to create user.'); return; }
        closeModal('userModal');
        document.getElementById('userDisplayName').value = '';
        document.getElementById('userName').value = '';
        document.getElementById('userPassword').value = '';
        document.getElementById('userRole').value = '';
        showToast((_t.user_created || 'User "{name}" created').replace('{name}', displayName));
        loadAdminData();
    } finally {
        btn.disabled = false; btn.textContent = _t.create_user || 'Create User';
    }
}

async function submitUpload() {
    clearModalError('upload');
    const farmId = document.getElementById('uploadFarm').value;
    const fileInput = document.getElementById('reportFile');
    if (!farmId) { setModalError('upload', _t.select_farm_error || 'Please select a farm.'); return; }
    if (!fileInput.files.length) { setModalError('upload', _t.select_file_error || 'Please choose a .json file.'); return; }

    const btn = document.getElementById('uploadBtn');
    btn.disabled = true; btn.textContent = _t.uploading || 'Uploading…';

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const res = await fetch(`/api/admin/farms/${farmId}/upload`, {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (!res.ok) { setModalError('upload', data.error || 'Upload failed.'); return; }
        closeModal('uploadModal');
        showToast((_t.report_uploaded || 'Report "{name}" uploaded').replace('{name}', data.filename));
        loadAdminData();
    } finally {
        btn.disabled = false; btn.textContent = _t.upload_report_title || 'Upload Report';
    }
}

// ---------------------------------------------------------------------------
// File drop zone
// ---------------------------------------------------------------------------

function onFileSelected(input) {
    if (input.files.length) {
        const name = input.files[0].name;
        document.getElementById('fileDropText').innerHTML =
            `<strong>${escHtml(name)}</strong><br><span style="font-size:0.8em;color:#40916c;">${_t.ready_to_upload || 'Ready to upload'}</span>`;
        document.getElementById('dropZone').classList.add('has-file');
    }
}

function setupDragDrop() {
    const zone = document.getElementById('dropZone');
    if (!zone) return;
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) {
            const input = document.getElementById('reportFile');
            const dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            onFileSelected(input);
        }
    });
}

// ---------------------------------------------------------------------------
// Refresh dropdowns after create
// ---------------------------------------------------------------------------

async function refreshDropdowns() {
    const [orgsRes, farmsRes] = await Promise.all([
        fetch('/api/admin/orgs/list'),
        fetch('/api/admin/farms/list'),
    ]);
    if (orgsRes.ok) _allOrgs = await orgsRes.json();
    if (farmsRes.ok) _allFarms = await farmsRes.json();

    // Update metric counters
    document.getElementById('metTotalOrgs').textContent = _allOrgs.length;
    document.getElementById('metTotalFarms').textContent = _allFarms.length;
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

let _toastTimer;
function showToast(msg, isError = false) {
    let toast = document.getElementById('adminToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'adminToast';
        toast.className = 'toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = 'toast' + (isError ? ' error' : '');
    clearTimeout(_toastTimer);
    requestAnimationFrame(() => {
        requestAnimationFrame(() => toast.classList.add('show'));
    });
    _toastTimer = setTimeout(() => toast.classList.remove('show'), 3500);
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function getStatusClass(score) {
    if (score >= 75) return 'good';
    if (score >= 65) return 'fair';
    return 'poor';
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        return isNaN(d) ? dateStr : d.toLocaleDateString();
    } catch { return dateStr; }
}

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
