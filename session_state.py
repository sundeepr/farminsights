import json
import os
import threading

_UPLOADS_BASE = 'data/uploads'
_BATCH_SIZE = 5

_session_locks: dict[str, threading.Lock] = {}
_locks_mutex = threading.Lock()


def _get_lock(session_id: str) -> threading.Lock:
    with _locks_mutex:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


def _state_path(session_id: str) -> str:
    return os.path.join(_UPLOADS_BASE, session_id, 'state.json')


def _load(session_id: str) -> dict:
    path = _state_path(session_id)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {'farm_id': None, 'pending': [], 'batches': []}


def _save(session_id: str, state: dict):
    with open(_state_path(session_id), 'w') as f:
        json.dump(state, f, indent=2)


def _make_batch_entry(state: dict, batch_files: list[str]) -> int:
    batch_index = len(state['batches']) + 1
    state['batches'].append({
        'batch_index': batch_index,
        'images': batch_files,
        'status': 'in_progress',
        'report_filename': None,
    })
    return batch_index


def _abs_paths(session_id: str, filenames: list[str]) -> list[str]:
    session_dir = os.path.join(_UPLOADS_BASE, session_id)
    return [os.path.abspath(os.path.join(session_dir, f)) for f in filenames]


def add_image(session_id: str, filename: str,
              farm_id: str | None = None) -> tuple[int, list[str], str | None] | None:
    """Add filename to pending list.

    Returns (batch_index, abs_image_paths, farm_id) when _BATCH_SIZE images
    are ready, otherwise None. Thread-safe per session.
    farm_id is stored on first call and reused for subsequent calls.
    """
    lock = _get_lock(session_id)
    with lock:
        state = _load(session_id)
        if farm_id and not state.get('farm_id'):
            state['farm_id'] = farm_id
        state['pending'].append(filename)
        if len(state['pending']) >= _BATCH_SIZE:
            batch_files = state['pending'][:_BATCH_SIZE]
            state['pending'] = state['pending'][_BATCH_SIZE:]
            batch_index = _make_batch_entry(state, batch_files)
            _save(session_id, state)
            return batch_index, _abs_paths(session_id, batch_files), state.get('farm_id')
        _save(session_id, state)
        return None


def flush_session(session_id: str) -> tuple[int, list[str], str | None] | None:
    """Dispatch all pending images (even < 5) as one batch.
    Returns (batch_index, abs_image_paths, farm_id) or None if nothing pending."""
    lock = _get_lock(session_id)
    with lock:
        state = _load(session_id)
        if not state['pending']:
            return None
        batch_files = state['pending'][:]
        state['pending'] = []
        batch_index = _make_batch_entry(state, batch_files)
        _save(session_id, state)
        return batch_index, _abs_paths(session_id, batch_files), state.get('farm_id')


def sessions_with_pending() -> list[str]:
    """Return all session_ids that have at least one pending image."""
    result = []
    if not os.path.exists(_UPLOADS_BASE):
        return result
    for session_id in os.listdir(_UPLOADS_BASE):
        path = _state_path(session_id)
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r') as f:
                state = json.load(f)
            if state.get('pending'):
                result.append(session_id)
        except Exception:
            pass
    return result


def mark_batch_complete(session_id: str, batch_index: int, report_filename: str):
    lock = _get_lock(session_id)
    with lock:
        state = _load(session_id)
        for batch in state['batches']:
            if batch['batch_index'] == batch_index:
                batch['status'] = 'completed'
                batch['report_filename'] = report_filename
                break
        _save(session_id, state)


def mark_batch_failed(session_id: str, batch_index: int, error: str):
    lock = _get_lock(session_id)
    with lock:
        state = _load(session_id)
        for batch in state['batches']:
            if batch['batch_index'] == batch_index:
                batch['status'] = 'failed'
                batch['error'] = error
                break
        _save(session_id, state)
