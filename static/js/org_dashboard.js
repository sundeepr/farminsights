/**
 * org_dashboard.js — Org metrics, tables, and management (create farm, upload report)
 */

let _orgId = null;
let _userRole = null;
let _scopedOrgs = [];
let _scopedFarms = [];
let _t = {};

document.addEventListener('DOMContentLoaded', () => {
    const el = document.getElementById('orgDashboard');
    if (!el) return;
    _orgId = el.dataset.orgId;
    _userRole = el.dataset.userRole;
    _t = window._t || {};
    loadOrgData();
    if (_userRole === 'admin' || _userRole === 'org_admin') {
        loadScopedLists();
        setupDragDrop();
    }
    // Close modals on overlay click
    document.querySelectorAll('.admin-modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', e => {
            if (e.target === overlay) overlay.style.display = 'none';
        });
    });
});

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadOrgData() {
    try {
        const res = await fetch(`/api/org/${_orgId}/summary`);
        if (!res.ok) return;
        const data = await res.json();
        renderMetrics(data);
        renderSubOrgs(data.children || []);
        renderFarms(data.farms || []);
    } catch (err) {
        console.error('Failed to load org summary:', err);
    }
}

async function loadScopedLists() {
    const [orgsRes, farmsRes] = await Promise.all([
        fetch(`/api/org/${_orgId}/orgs/list`),
        fetch(`/api/org/${_orgId}/farms/list`),
    ]);
    if (orgsRes.ok) _scopedOrgs = await orgsRes.json();
    if (farmsRes.ok) _scopedFarms = await farmsRes.json();
}

// ---------------------------------------------------------------------------
// Table renderers
// ---------------------------------------------------------------------------

function renderMetrics(data) {
    const avgHealth = data.avg_health;
    const avgEl = document.getElementById('metAvgHealth');
    const statusEl = document.getElementById('metHealthStatus');

    if (avgHealth !== null) {
        let cls = 'poor', label = _t.poor || 'Poor';
        if (avgHealth >= 75) { cls = 'good'; label = _t.good || 'Good'; }
        else if (avgHealth >= 65) { cls = 'fair'; label = _t.fair || 'Fair'; }
        avgEl.innerHTML = `<span class="${cls}">${avgHealth}</span>`;
        if (avgHealth >= 75) { statusEl.textContent = _t.good_overall_health || 'Good overall health'; }
        else if (avgHealth >= 65) { statusEl.textContent = _t.fair_overall_health || 'Fair overall health'; }
        else { statusEl.textContent = _t.poor_overall_health || 'Poor overall health'; }
    } else {
        avgEl.textContent = _t.na || 'N/A';
        statusEl.textContent = _t.no_data_available || 'No data available';
    }

    document.getElementById('metFarmCount').textContent = data.farm_count;
    document.getElementById('metFarmSub').textContent =
        data.farm_count === 1 ? `1 ${_t.farm_in_this_org || 'farm in this org'}` : `${data.farm_count} ${_t.farms_in_this_org || 'farms in this org'}`;
    document.getElementById('metAlerts').textContent = data.issues_count;

    const lastEl = document.getElementById('metLastReport');
    if (data.last_report_date) {
        try {
            const d = new Date(data.last_report_date);
            lastEl.textContent = isNaN(d) ? data.last_report_date : d.toLocaleDateString();
        } catch { lastEl.textContent = data.last_report_date; }
    } else {
        lastEl.textContent = _t.no_reports_yet || 'No reports yet';
    }
}

function renderSubOrgs(children) {
    const card = document.getElementById('subOrgsCard');
    if (!children.length) return;
    card.style.display = 'block';
    const tbody = document.getElementById('subOrgsBody');
    tbody.innerHTML = '';
    children.forEach(child => {
        const health = child.avg_health !== null ? child.avg_health : '—';
        const status = child.avg_health !== null ? getStatusClass(child.avg_health) : 'unknown';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escHtml(child.org_name)}</strong></td>
            <td>${child.farm_count}</td>
            <td><span class="metric-value ${status}" style="font-size:1em;">${health}</span></td>
            <td>${child.issues_count}</td>
            <td>${formatDate(child.last_report_date)}</td>
            <td><a href="/org/${escHtml(child.org_id)}" class="btn-action">${_t.view || 'View'}</a></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderFarms(farms) {
    const tbody = document.getElementById('farmsBody');
    if (!farms.length) {
        const canManage = _userRole === 'admin' || _userRole === 'org_admin';
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#adb5bd;padding:30px;">${canManage ? (_t.no_farms_manage || 'No farms yet.') : (_t.no_farms_in_org || 'No farms in this organization.')}</td></tr>`;
        return;
    }
    tbody.innerHTML = '';
    farms.forEach(farm => {
        const health = farm.avg_health !== null ? farm.avg_health : null;
        const statusClass = health !== null ? getStatusClass(health) : 'unknown';
        const canManage = _userRole === 'admin' || _userRole === 'org_admin';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escHtml(farm.farm_name)}</strong></td>
            <td>${health !== null ? health : '—'}</td>
            <td><span class="badge badge-${statusClass}">${farm.status}</span></td>
            <td>${farm.issues_count}</td>
            <td class="weather-cell" id="wx-${escHtml(farm.farm_id)}"><span style="color:#adb5bd;font-size:0.8em;">${_t.loading_ellipsis || 'Loading…'}</span></td>
            <td class="rain-cell" id="rain-${escHtml(farm.farm_id)}"><span style="color:#adb5bd;font-size:0.8em;">—</span></td>
            <td class="farmers-cell" id="farmers-${escHtml(farm.farm_id)}"><span style="color:#adb5bd;font-size:0.8em;">—</span></td>
            <td>${formatDate(farm.last_report_date)}</td>
            <td>
                <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:center;">
                    <a href="/farm/${escHtml(farm.farm_id)}" class="btn-action">${_t.more_details || 'More Details'}</a>
                    ${canManage ? `<button class="btn-action" style="background:linear-gradient(135deg,#1565c0,#1976d2);" onclick="openUploadForFarm('${escHtml(farm.farm_id)}')">${_t.upload_short || '↑ Upload'}</button>` : ''}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
        fetchWeatherForFarm(farm.farm_id);
        fetchFarmersForFarm(farm.farm_id);
    });
}

async function fetchWeatherForFarm(farmId) {
    try {
        const res = await fetch(`/api/weather/${farmId}`);
        if (!res.ok) throw new Error('failed');
        const w = await res.json();
        if (w.error) throw new Error(w.error);
        const wxCell = document.getElementById(`wx-${farmId}`);
        const rainCell = document.getElementById(`rain-${farmId}`);
        if (wxCell) {
            const wmoKey = `wmo_${w.weather_code}`;
            const description = (w.weather_code !== null && w.weather_code !== undefined && _t[wmoKey])
                ? _t[wmoKey] : w.description;
            const sparkline = buildSparkline(w.temp_24h || []);
            wxCell.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:center;gap:8px;">
                    <div>
                        <div>${w.icon} ${w.temperature !== null ? '<strong>' + w.temperature + '°C</strong>' : '—'}</div>
                        <div style="color:#6c757d;font-size:0.75em;">${description}</div>
                    </div>
                    ${sparkline}
                </div>`;
        }
        if (rainCell) {
            const prob = w.rain_prob_24h ?? 0;
            const color = prob >= 60 ? '#1565c0' : prob >= 30 ? '#1976d2' : '#adb5bd';
            rainCell.innerHTML = `<span style="font-weight:600;color:${color};">${prob}%</span>`;
        }
    } catch {
        const wxCell = document.getElementById(`wx-${farmId}`);
        if (wxCell) wxCell.innerHTML = `<span style="color:#adb5bd;font-size:0.8em;">${_t.na || 'N/A'}</span>`;
    }
}

function buildSparkline(temps) {
    if (!temps || temps.length < 2) return '';
    const W = 80, H = 32, pad = 2;
    const min = Math.min(...temps);
    const max = Math.max(...temps);
    const range = max - min || 1;
    const points = temps.map((t, i) => {
        const x = pad + (i / (temps.length - 1)) * (W - pad * 2);
        const y = pad + (1 - (t - min) / range) * (H - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const minTemp = min.toFixed(1);
    const maxTemp = max.toFixed(1);
    return `<div title="24h temp: ${minTemp}°C – ${maxTemp}°C">
        <svg width="${W}" height="${H}" style="display:block;overflow:visible;">
            <polyline points="${points}"
                fill="none" stroke="#40916c" stroke-width="1.5"
                stroke-linejoin="round" stroke-linecap="round"/>
            <text x="0" y="${H}" font-size="8" fill="#adb5bd">${minTemp}°</text>
            <text x="0" y="8" font-size="8" fill="#adb5bd">${maxTemp}°</text>
        </svg>
    </div>`;
}

async function fetchFarmersForFarm(farmId) {
    try {
        const res = await fetch(`/api/farm/${farmId}/farmers`);
        if (!res.ok) return;
        const farmers = await res.json();
        const cell = document.getElementById(`farmers-${farmId}`);
        if (!cell) return;
        if (!farmers.length) {
            cell.innerHTML = `<span style="color:#adb5bd;font-size:0.8em;">${_t.none || 'None'}</span>`;
            return;
        }
        const names = farmers.map(f => escHtml(f.username)).join(', ');
        const farmerLabel = farmers.length === 1 ? (_t.farmer || 'farmer') : (_t.farmers || 'farmers');
        cell.innerHTML = `<span style="cursor:pointer;color:#1976d2;" title="${names}" onclick="openFarmersModal('${escHtml(farmId)}', ${JSON.stringify(farmers).replace(/"/g, '&quot;')})">${farmers.length} ${farmerLabel}</span>`;
    } catch { /* silently ignore */ }
}

// ---------------------------------------------------------------------------
// Farmers modal
// ---------------------------------------------------------------------------

function openFarmersModal(farmId, farmers) {
    const farmName = document.querySelector(`#farmers-${farmId}`)?.closest('tr')?.querySelector('td:first-child strong')?.textContent || farmId;
    document.getElementById('farmersModalTitle').textContent = `${_t.farmers_title || 'Farmers'} — ${farmName}`;
    const body = document.getElementById('farmersModalBody');
    if (!farmers || !farmers.length) {
        body.innerHTML = `<div style="color:#adb5bd;padding:10px;">${_t.no_farmers || 'No farmers assigned to this farm.'}</div>`;
    } else {
        body.innerHTML = `<table class="data-table"><thead><tr><th>${_t.username_col || 'Username'}</th><th>${_t.role || 'Role'}</th></tr></thead><tbody>
            ${farmers.map(f => `<tr><td><strong>${escHtml(f.username)}</strong></td><td><span class="badge badge-${escHtml(f.role)}">${escHtml(f.role).replace('_',' ')}</span></td></tr>`).join('')}
        </tbody></table>`;
    }
    showModal('farmersModal');
}
function closeFarmersModal() { hideModal('farmersModal'); }

// ---------------------------------------------------------------------------
// Modal open/close
// ---------------------------------------------------------------------------

function openFarmModal() {
    const container = document.getElementById('farmOrgCheckboxes');
    if (container) {
        container.innerHTML = '';
        _scopedOrgs.forEach(o => {
            const label = document.createElement('label');
            label.innerHTML = `<input type="checkbox" value="${escHtml(o.id)}"> ${escHtml(o.name)}`;
            container.appendChild(label);
        });
    }
    showModal('farmModal');
}
function closeFarmModal() { hideModal('farmModal'); }

function openUploadModal() {
    populateSelect('uploadFarm', _scopedFarms, '— Select farm —');
    resetFilePicker();
    showModal('uploadModal');
}
function closeUploadModal() { hideModal('uploadModal'); }

function openUploadForFarm(farmId) {
    openUploadModal();
    document.getElementById('uploadFarm').value = farmId;
}

function showModal(id) { document.getElementById(id).style.display = 'flex'; }
function hideModal(id) {
    document.getElementById(id).style.display = 'none';
    const err = document.getElementById(id.replace('Modal', 'ModalError'));
    if (err) err.style.display = 'none';
}

function populateSelect(selectId, items, placeholder) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML = `<option value="">${placeholder}</option>`;
    items.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = item.name;
        sel.appendChild(opt);
    });
}

function setModalError(prefix, msg) {
    const el = document.getElementById(`${prefix}ModalError`);
    if (el) { el.textContent = msg; el.style.display = 'block'; }
}

// ---------------------------------------------------------------------------
// Submit handlers
// ---------------------------------------------------------------------------

async function submitCreateFarm() {
    const name = document.getElementById('farmName').value.trim();
    const orgIds = [...document.querySelectorAll('#farmOrgCheckboxes input:checked')].map(el => el.value);
    const lat = document.getElementById('farmLat').value;
    const lng = document.getElementById('farmLng').value;
    if (!name) { setModalError('farm', _t.farm_name_required || 'Farm name is required.'); return; }
    if (!orgIds.length) { setModalError('farm', _t.select_at_least_one_org || 'Please select at least one organization.'); return; }

    const btn = document.getElementById('farmSubmitBtn');
    btn.disabled = true; btn.textContent = _t.creating || 'Creating…';
    try {
        const res = await fetch('/api/admin/farms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, org_ids: orgIds, lat: lat || null, lng: lng || null }),
        });
        const data = await res.json();
        if (!res.ok) { setModalError('farm', data.error || 'Failed.'); return; }
        closeFarmModal();
        document.getElementById('farmName').value = '';
        document.getElementById('farmLat').value = '';
        document.getElementById('farmLng').value = '';
        showToast((_t.farm_created || 'Farm "{name}" created').replace('{name}', name));
        await loadScopedLists();
        loadOrgData();
    } finally { btn.disabled = false; btn.textContent = 'Create Farm'; }
}

async function submitUpload() {
    const farmId = document.getElementById('uploadFarm').value;
    const fileInput = document.getElementById('reportFile');
    if (!farmId) { setModalError('upload', _t.select_farm_error || 'Please select a farm.'); return; }
    if (!fileInput.files.length) { setModalError('upload', _t.select_file_error || 'Please choose a .json file.'); return; }

    const btn = document.getElementById('uploadBtn');
    btn.disabled = true; btn.textContent = _t.uploading || 'Uploading…';
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    try {
        const res = await fetch(`/api/admin/farms/${farmId}/upload`, { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) { setModalError('upload', data.error || 'Upload failed.'); return; }
        closeUploadModal();
        showToast((_t.report_uploaded || 'Report "{name}" uploaded').replace('{name}', data.filename));
        loadOrgData();
    } finally { btn.disabled = false; btn.textContent = 'Upload Report'; }
}

// ---------------------------------------------------------------------------
// File drop zone
// ---------------------------------------------------------------------------

function onFileSelected(input) {
    if (input.files.length) {
        document.getElementById('fileDropText').innerHTML =
            `<strong>${escHtml(input.files[0].name)}</strong><br><span style="font-size:0.8em;color:#40916c;">${_t.ready_to_upload || 'Ready to upload'}</span>`;
        document.getElementById('dropZone').classList.add('has-file');
    }
}

function resetFilePicker() {
    const input = document.getElementById('reportFile');
    if (input) input.value = '';
    const text = document.getElementById('fileDropText');
    if (text) text.innerHTML = `${_t.click_to_choose || 'Click to choose a .json file'}<br><span style="font-size:0.8em;color:#adb5bd;">${_t.or_drag_drop || 'or drag and drop here'}</span>`;
    const zone = document.getElementById('dropZone');
    if (zone) zone.classList.remove('has-file');
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
// Toast
// ---------------------------------------------------------------------------

let _toastTimer;
function showToast(msg, isError = false) {
    let toast = document.getElementById('orgToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'orgToast';
        toast.className = 'toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = 'toast' + (isError ? ' error' : '');
    clearTimeout(_toastTimer);
    requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add('show')));
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
