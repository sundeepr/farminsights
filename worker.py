import json
import logging
import os
import queue
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener
from google import genai
from google.genai import types

import session_state

register_heif_opener()

logger = logging.getLogger(__name__)

batch_queue: queue.Queue = queue.Queue()

_UPLOADS_BASE = 'data/uploads'
_GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash-preview-04-17')
_FARM_CROP = os.environ.get('FARM_CROP') or None

_gemini_client: Optional[genai.Client] = None
_gemini_lock = threading.Lock()


def _get_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        with _gemini_lock:
            if _gemini_client is None:
                _gemini_client = genai.Client(
                    http_options={'api_version': 'v1alpha'}
                )
    return _gemini_client


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

def _to_jpeg_bytes(image_path: Path) -> bytes:
    """Convert any supported image format to a resized JPEG byte payload."""
    try:
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        max_side = 1024
        ratio = max_side / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=90, optimize=True)
        return buf.getvalue()
    except Exception:
        with open(image_path, 'rb') as f:
            return f.read()


def _extract_metadata(image_path: Path, gps_index: dict) -> dict:
    """Extract EXIF metadata; GPS coordinates come from gps_index."""
    try:
        img = Image.open(image_path)
        exif = img.getexif()

        metadata: dict = {
            'image_name': image_path.name,
            'file_size_mb': round(image_path.stat().st_size / (1024 * 1024), 3),
            'image_dimensions': {'width': img.width, 'height': img.height},
        }

        timestamp = None
        camera = {}
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag in ('DateTime', 'DateTimeOriginal', 'DateTimeDigitized') and not timestamp:
                try:
                    timestamp = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                except ValueError:
                    pass
            elif tag in ('Make', 'Model', 'LensModel'):
                camera[tag.lower()] = str(value)

        metadata['timestamp'] = timestamp.isoformat() if timestamp else None
        if camera:
            metadata['camera'] = camera

        gps_entry = gps_index.get(image_path.name)
        metadata['gps_coordinates'] = gps_entry['gps_coordinates'] if gps_entry else None

        return metadata
    except Exception as e:
        return {'image_name': image_path.name, 'error': str(e)}


# ---------------------------------------------------------------------------
# Gemini analysis
# ---------------------------------------------------------------------------

def _analyze_with_gemini(image_paths: list[Path], model: str, crop: Optional[str]) -> list[dict]:
    """Send a batch of images to Gemini and return per-image analysis dicts."""
    client = _get_client()
    start = time.time()

    crop_info = (f"The images are of {crop} plants." if crop
                 else "Please identify the crop shown in each image.")
    prompt = f"""You are an expert agricultural consultant analyzing plant health. \
I am providing {len(image_paths)} images. {crop_info}

For EACH image, provide a detailed assessment. Respond ONLY with a valid JSON array \
containing one object per image in order:

[
    {{
        "image_name": "<filename of the image>",
        "health_score": <0-100, where 0=dead plant, 100=perfectly healthy>,
        "health_status": "<one of: excellent, good, fair, poor, critical, dead>",
        "issues_detected": "<diseases, pests, nutrient deficiencies, water stress, \
physical damage. If healthy: 'No significant issues detected'>",
        "recommended_interventions": "<specific actionable recommendations>",
        "visual_observations": "<plant type if identifiable, color, growth stage, \
leaf condition>"
    }}
]

Consider:
- Assume adequate soil moisture unless clear water-stress symptoms are visible.
- Leaf color and texture, signs of disease or pest damage, growth patterns, plant vigor."""

    contents: list = [prompt]
    for i, path in enumerate(image_paths):
        contents.append(f"\nImage {i + 1}: {path.name}")
        contents.append(types.Part.from_bytes(
            data=_to_jpeg_bytes(path),
            mime_type='image/jpeg',
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        ))

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type='application/json',
        ),
    )

    elapsed = round(time.time() - start, 2)
    per_image = round(elapsed / len(image_paths), 2)
    response_text = (response.text or '').strip()

    try:
        # Strip markdown fences if present
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        analyses = json.loads(response_text)
        if isinstance(analyses, dict):
            for v in analyses.values():
                if isinstance(v, list):
                    analyses = v
                    break
        if not isinstance(analyses, list):
            analyses = [analyses]

        results = []
        for i, path in enumerate(image_paths):
            if i < len(analyses):
                item = analyses[i]
                if 'health_score' in item:
                    item['health_score'] = max(0.0, min(100.0, float(item['health_score'])))
                item['processing_time_seconds'] = per_image
                results.append(item)
            else:
                results.append({
                    'health_score': None,
                    'health_status': 'error',
                    'issues_detected': 'No analysis returned for this image in batch',
                    'recommended_interventions': 'Manual inspection required',
                    'processing_time_seconds': per_image,
                    'error': 'Missing from batch response',
                })
        return results

    except (json.JSONDecodeError, ValueError) as e:
        return [{
            'health_score': None,
            'health_status': 'unknown',
            'issues_detected': 'Error parsing model response',
            'recommended_interventions': 'Manual inspection required',
            'processing_time_seconds': per_image,
            'error': f'JSON parse error: {e}',
            'raw_response': response_text if i == 0 else '',
        } for i in range(len(image_paths))]


# ---------------------------------------------------------------------------
# GPS metadata loader
# ---------------------------------------------------------------------------

def _load_gps_index(session_id: str, filenames: list[str]) -> dict:
    """Return a dict mapping filename → {gps_coordinates: {...}} from gps.jsonl."""
    gps_path = os.path.join(_UPLOADS_BASE, session_id, 'gps.jsonl')
    index: dict = {}
    if not os.path.exists(gps_path):
        return index
    with open(gps_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                fname = entry.get('image_filename')
                if not fname:
                    continue
                gps: dict = {'latitude': entry['latitude'], 'longitude': entry['longitude']}
                if entry.get('altitude') is not None:
                    gps['altitude'] = entry['altitude']
                index[fname] = {'gps_coordinates': gps}
            except Exception:
                pass
    return {f: index[f] for f in filenames if f in index}


# ---------------------------------------------------------------------------
# Batch entry point
# ---------------------------------------------------------------------------

def process_batch(session_id: str, batch_index: int, image_paths: list[str]) -> dict:
    """Analyze a batch of images and return a health report dict."""
    paths = [Path(p) for p in image_paths]
    filenames = [p.name for p in paths]
    gps_index = _load_gps_index(session_id, filenames)

    metadata_list = [_extract_metadata(p, gps_index) for p in paths]
    analyses = _analyze_with_gemini(paths, _GEMINI_MODEL, _FARM_CROP)

    images = [
        {**meta, 'plant_health_analysis': analysis}
        for meta, analysis in zip(metadata_list, analyses)
    ]

    successful = sum(
        1 for img in images
        if img.get('plant_health_analysis', {}).get('health_score') is not None
    )

    return {
        'report_metadata': {
            'generated_at': datetime.utcnow().isoformat(),
            'session_id': session_id,
            'batch_index': batch_index,
            'model_used': _GEMINI_MODEL,
            'total_images': len(images),
            'successful_analyses': successful,
            'status': 'completed',
        },
        'images': images,
    }


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

def _save_report(session_id: str, batch_index: int, report: dict) -> str:
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'report_batch_{batch_index}_{timestamp}.json'
    with open(os.path.join(_UPLOADS_BASE, session_id, filename), 'w') as f:
        json.dump(report, f, indent=2)
    return filename


def worker_loop():
    while True:
        job = batch_queue.get()
        session_id, batch_index, image_paths = job
        try:
            logger.info('Processing batch %d for session %s (%d images)',
                        batch_index, session_id, len(image_paths))
            report = process_batch(session_id, batch_index, image_paths)
            report_filename = _save_report(session_id, batch_index, report)
            session_state.mark_batch_complete(session_id, batch_index, report_filename)
            logger.info('Batch %d for session %s complete → %s',
                        batch_index, session_id, report_filename)
        except Exception as e:
            logger.error('Batch %d for session %s failed: %s', batch_index, session_id, e)
            session_state.mark_batch_failed(session_id, batch_index, str(e))
        finally:
            batch_queue.task_done()


def flush_pending(interval_minutes: int):
    while True:
        time.sleep(interval_minutes * 60)
        for sid in session_state.sessions_with_pending():
            result = session_state.flush_session(sid)
            if result:
                batch_index, image_paths = result
                batch_queue.put((sid, batch_index, image_paths))
                logger.info('Flush: queued %d image(s) for session %s as batch %d',
                            len(image_paths), sid, batch_index)


def start_worker(flush_interval_minutes: int = 5):
    threading.Thread(target=worker_loop, daemon=True, name='batch-worker').start()
    threading.Thread(target=flush_pending, args=(flush_interval_minutes,),
                     daemon=True, name='flush-timer').start()
    logger.info('Worker started (flush interval: %d min)', flush_interval_minutes)
