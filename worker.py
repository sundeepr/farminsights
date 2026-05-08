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
import config_loader

_SUMMARY_PROMPT = """You are an expert agricultural report data generator.

Your task is to read the provided crop-health analysis JSON and convert it into a clean, field-level report-data JSON that will be used by a PDF generation script.

The input JSON contains:
- report_metadata
- image-level GPS coordinates
- image-level plant health scores
- image-level health status
- image-level issues detected
- image-level recommended interventions
- image-level visual observations
- possible failed analyses where health_score is null or health_status is "unknown"

You must NOT generate a PDF.
You must ONLY return valid JSON.
Do not include markdown, comments, explanations, or extra text.

========================
CORE OBJECTIVE
========================

Create a farmer-ready, field-level crop advisory report in two languages:

1. English
2. Marathi

The report must summarize the entire field, not individual images.

The final JSON will be consumed by a PDF renderer, so the output must be structured, concise, and deterministic.

========================
INPUT HANDLING RULES
========================

1. Use only valid image analyses for agronomic conclusions:
   - Include images where plant_health_analysis.health_score is a number.
   - Exclude images where health_score is null.
   - Exclude images where health_status is "unknown".
   - Exclude images where issues_detected contains "Error parsing model response".

2. Still count the following separately:
   - total_images from report_metadata.total_images
   - successful_analyses from report_metadata.successful_analyses
   - valid_images_used_for_summary = number of usable records after filtering

3. Use GPS coordinates only:
   - Extract all valid latitude and longitude values.
   - Compute the median latitude.
   - Compute the median longitude.
   - Do NOT infer village, district, state, or country.
   - Do NOT use reverse geocoding.

4. Determine assessment date:
   - Prefer the earliest valid image timestamp date if available.
   - Otherwise use report_metadata.generated_at date.
   - Format English date as: "18 Jan 2026"
   - Format Marathi date in Marathi numerals and month name if possible.

5. Crop name and growth stage:
   - If crop name is explicitly present in the JSON, use it.
   - If crop name is repeatedly mentioned in visual_observations, infer it only if confidence is high.
   - If uncertain, use "Crop not specified".
   - Infer growth stage only from repeated visual observations.
   - Examples: seedling, early vegetative, flowering, early fruiting.
   - If uncertain, use "Not specified".

========================
FIELD-LEVEL ANALYSIS RULES
========================

You must synthesize image-level data into field-level insights.

1. Overall health score:
   - Calculate average_health_score from all valid images.
   - Also calculate median_health_score.
   - Use these thresholds for field_health_status:
     - 80-100: Good
     - 60-79: Fair
     - 40-59: Poor
     - 0-39: Critical

2. Health summary:
   - Write a short field-level summary.
   - Do not list every image.
   - Mention whether crop condition is uniform or uneven.
   - Mention dominant stress patterns.

3. Key issues:
   - Aggregate repeated issue themes from issues_detected and visual_observations.
   - Group similar terms:
     - "yellowing", "nitrogen deficiency", "nutrient deficiency", "micronutrient deficiency" -> Nutrition deficiency
     - "dry soil", "water stress", "moisture stress", "irrigation" -> Moisture stress
     - "weeds", "weed competition" -> Weed competition
     - "pest damage", "holes", "aphids", "mites", "thrips", "whiteflies" -> Pest pressure
     - "leaf curl", "mottling", "viral symptoms" -> Possible viral symptoms
     - "wilting", "stunted", "weak growth" -> Weak establishment

4. Prioritize issues:
   - Rank issues by frequency and severity.
   - Mark one issue as primary_issue.
   - Mark other issues as secondary_issues.
   - Do not exaggerate.
   - Use "possible" when the evidence is not conclusive.

5. Recommendations:
   - Generate field-level recommendations for the next 5-7 days.
   - Provide both organic and non-organic options where possible.
   - Keep recommendations practical for farmers.
   - Do not recommend restricted, dangerous, or highly specific pesticide dosages unless clearly supported.
   - For pest/disease, recommend inspection first unless evidence is repeated and strong.
   - Include roguing only when viral symptoms or severely distorted plants are observed.

6. Expected outcome:
   - Provide realistic expected outcomes.
   - Mention time range such as 7-10 days only for visible recovery indicators.
   - Do not guarantee yield improvement.

========================
LANGUAGE RULES
========================

1. English:
   - Use clear farmer-friendly language.
   - Keep sentences short.
   - Avoid technical jargon unless necessary.

2. Marathi:
   - Use natural Marathi suitable for farmers.
   - Do not mix English words unless unavoidable.
   - Marathi text must be Unicode Devanagari.
   - Do not transliterate Marathi using Latin letters.
   - Keep the Marathi version semantically equivalent to English.
   - Use Marathi labels, not English labels.

========================
OUTPUT JSON SCHEMA
========================

Return JSON exactly in this structure:

{
  "report_metadata": {
    "report_title": "",
    "crop_name": "",
    "crop_growth_stage": "",
    "assessment_date": "",
    "field_location_median_gps": {"latitude": 0.0, "longitude": 0.0},
    "total_images": 0,
    "successful_analyses": 0,
    "valid_images_used_for_summary": 0,
    "model_used": "",
    "data_quality_notes": []
  },
  "computed_metrics": {
    "average_health_score": 0.0,
    "median_health_score": 0.0,
    "min_health_score": 0.0,
    "max_health_score": 0.0,
    "field_health_status": "",
    "issue_frequency": {
      "weed_competition": 0, "nutrition_deficiency": 0, "moisture_stress": 0,
      "pest_pressure": 0, "possible_viral_symptoms": 0, "weak_establishment": 0
    }
  },
  "english_report": {
    "title": "",
    "header": {"crop_name": "", "crop_growth_stage": "", "assessment_date": "", "field_location": "", "images_analyzed": ""},
    "overall_field_health": {"health_status": "", "summary_points": []},
    "key_issues_observed": [],
    "recommended_interventions_next_5_7_days": [
      {"area": "Weed Control", "organic_option": "", "non_organic_option": ""},
      {"area": "Nutrition", "organic_option": "", "non_organic_option": ""},
      {"area": "Pest / Disease", "organic_option": "", "non_organic_option": ""},
      {"area": "Roguing / Plant Removal", "organic_option": "", "non_organic_option": ""}
    ],
    "expected_outcome": []
  },
  "marathi_report": {
    "title": "",
    "header": {"crop_name": "", "crop_growth_stage": "", "assessment_date": "", "field_location": "", "images_analyzed": ""},
    "overall_field_health": {"health_status": "", "summary_points": []},
    "key_issues_observed": [],
    "recommended_interventions_next_5_7_days": [
      {"area": "\\u0924\\u0923 \\u0928\\u093f\\u092f\\u0902\\u0924\\u094d\\u0930\\u0923", "organic_option": "", "non_organic_option": ""},
      {"area": "\\u092a\\u094b\\u0937\\u0923", "organic_option": "", "non_organic_option": ""},
      {"area": "\\u0915\\u0940\\u0921 / \\u0930\\u094b\\u0917", "organic_option": "", "non_organic_option": ""},
      {"area": "\\u091d\\u093e\\u0921\\u0947 \\u0915\\u093e\\u0922\\u0923\\u0947", "organic_option": "", "non_organic_option": ""}
    ],
    "expected_outcome": []
  }
}

========================
STYLE CONSTRAINTS
========================

- Keep each summary point under 18 words.
- Keep each key issue under 12 words.
- Keep each intervention cell under 25 words.
- Keep expected outcomes under 12 words each.
- Do not mention individual image names.
- Do not mention bounding boxes.
- Do not mention processing time.
- Do not mention model errors except in data_quality_notes.
- Do not invent exact chemical recommendations if the input is weak.
- Do not overstate disease diagnosis from visual symptoms alone.
- Use "possible" or "likely" where appropriate.

========================
FINAL OUTPUT REQUIREMENT
========================

Return only valid JSON.
No markdown.
No explanation.
No surrounding text.

Here is the crop-health analysis JSON:
"""

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
    """Convert any supported image format to JPEG bytes."""
    try:
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
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

def _save_report(save_dir: str, report: dict) -> str:
    """Save report to save_dir. Returns the filename."""
    timestamp = datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f'plant_health_report_{timestamp}.json'
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, filename), 'w') as f:
        json.dump(report, f, indent=2)
    return filename


def _resolve_save_dir(session_id: str, farm_id: str | None) -> str:
    """Return the directory where the report should be saved.
    If farm_id is provided and valid, save to the farm's data_folder.
    Otherwise fall back to the session uploads folder.
    """
    if farm_id:
        farm = config_loader.get_farm(farm_id)
        if farm and farm.get('data_folder'):
            return farm['data_folder']
    return os.path.join(_UPLOADS_BASE, session_id)


def worker_loop():
    while True:
        job = batch_queue.get()
        session_id, batch_index, image_paths, farm_id = job
        try:
            logger.info('Processing batch %d for session %s (%d images) → farm %s',
                        batch_index, session_id, len(image_paths), farm_id)
            report = process_batch(session_id, batch_index, image_paths)
            save_dir = _resolve_save_dir(session_id, farm_id)
            report_filename = _save_report(save_dir, report)
            session_state.mark_batch_complete(session_id, batch_index, report_filename)
            logger.info('Batch %d for session %s complete → %s/%s',
                        batch_index, session_id, save_dir, report_filename)
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
                batch_index, image_paths, farm_id = result
                batch_queue.put((sid, batch_index, image_paths, farm_id))
                logger.info('Flush: queued %d image(s) for session %s as batch %d',
                            len(image_paths), sid, batch_index)


def generate_report_summary(report_data: dict, summary_path: str) -> dict:
    """Call Gemini to generate a field-level summary and save as JSON.

    Raises on failure — caller should catch and handle.
    """
    client = _get_client()
    contents = [_SUMMARY_PROMPT, json.dumps(report_data, ensure_ascii=False)]
    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type='application/json',
        ),
    )
    response_text = (response.text or '').strip()
    if '```json' in response_text:
        response_text = response_text.split('```json')[1].split('```')[0].strip()
    elif '```' in response_text:
        response_text = response_text.split('```')[1].split('```')[0].strip()
    summary = json.loads(response_text)
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info('Summary saved → %s', summary_path)
    return summary


def start_worker(flush_interval_minutes: int = 5):
    threading.Thread(target=worker_loop, daemon=True, name='batch-worker').start()
    threading.Thread(target=flush_pending, args=(flush_interval_minutes,),
                     daemon=True, name='flush-timer').start()
    logger.info('Worker started (flush interval: %d min)', flush_interval_minutes)
