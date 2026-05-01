# FarmInsights REST API

Base URL: `http://<host>:5000`

All API responses use `Content-Type: application/json`.

---

## Authentication

The server uses **session cookies** for authentication. On Android, use OkHttp with a `CookieJar` (e.g. `JavaNetCookieJar`) so the session cookie is automatically stored and sent with every request.

### Roles

| Role | Access |
|------|--------|
| `admin` | All orgs, farms, users |
| `org_admin` | Assigned org and all descendants |
| `user` | Explicitly assigned farms only |

---

## Auth Endpoints

### `POST /api/login`

Authenticate and start a session.

**Request body:**
```json
{ "username": "admin", "password": "admin123" }
```

**Response `200`:**
```json
{
  "ok": true,
  "role": "admin",
  "redirect_url": "/admin",
  "user": {
    "id": "u1",
    "username": "admin",
    "display_name": "Administrator",
    "role": "admin",
    "org_id": null,
    "farm_ids": []
  }
}
```

**Response `401`:** `{ "error": "Invalid username or password" }`

---

### `POST /api/logout`

End the current session.

**Response `200`:** `{ "ok": true }`

---

### `GET /api/me`

Get current authenticated user.

**Response `200`:**
```json
{
  "id": "u1",
  "username": "admin",
  "display_name": "Administrator",
  "role": "admin",
  "org_id": null,
  "farm_ids": []
}
```

**Response `401`:** `{ "error": "Not authenticated" }`

---

### `POST /api/set-lang`

Set session language. Supported: `en`, `hi`, `te`, `mr`.

**Request body:** `{ "lang": "hi" }`

**Response `200`:** `{ "ok": true, "lang": "hi" }`

---

## Farm Endpoints

### `GET /api/farms`  *(new)*

List all farms accessible to the current user.

**Auth:** Required (any role)

**Response `200`:**
```json
[
  { "id": "farm_001", "name": "Sunrise Farm", "org_ids": ["org_002"], "lat": 17.709, "lng": 78.423 },
  ...
]
```

---

### `GET /api/farm/<farm_id>`  *(new)*

Get details for a single farm.

**Auth:** Required + must have farm access

**Response `200`:**
```json
{ "id": "farm_001", "name": "Sunrise Farm", "org_ids": ["org_002"], "lat": 17.709, "lng": 78.423 }
```

**Response `403`:** Forbidden | **Response `404`:** Farm not found

---

### `GET /api/farm/<farm_id>/summary`  *(new)*

Get health summary for a single farm (computed from the most recent report file).

**Auth:** Required + must have farm access

**Response `200`:**
```json
{
  "farm_id": "farm_001",
  "farm_name": "Sunrise Farm",
  "avg_health": 78.5,
  "issues_count": 3,
  "total_images": 85,
  "last_report_date": "2024-11-10T08:30:00",
  "status": "good",
  "file_count": 4
}
```

Status values: `good` (≥75), `fair` (65–74), `poor` (<65), `no_data`, `unknown`, `error`

---

### `GET /api/farm/<farm_id>/farmers`

Get users assigned to a farm.

**Auth:** Required + farm access

**Response `200`:**
```json
[
  { "id": "u3", "username": "farmer1", "display_name": "Ravi Kumar", "role": "user", "farm_ids": ["farm_001"] }
]
```

---

### `GET /api/files?farm_id=<farm_id>`

List available health report files for a farm.

**Auth:** Required + farm access

**Response `200`:**
```json
[
  { "filename": "report_2024_11_10.json", "display": "report 2024 11 10" },
  ...
]
```

---

### `GET /api/data/<farm_id>/<filename>`

Fetch a specific health report file.

**Auth:** Required + farm access

**Response `200`:** Full plant health report JSON (see [Data Models](#data-models))

---

### `GET /api/weather/<farm_id>`

Get current weather and 24h rain forecast for a farm (farm must have `lat`/`lng` set).

**Auth:** Required + farm access

**Response `200`:**
```json
{
  "temperature": 28.4,
  "humidity": 72,
  "wind_speed": 12.3,
  "precipitation": 0.0,
  "weather_code": 2,
  "weather_description": "Partly cloudy",
  "weather_icon": "⛅",
  "rain_probability_24h": 35
}
```

**Response `400`:** Farm has no GPS coordinates | **Response `502`:** Weather service error

---

## Organization Endpoints

### `GET /api/orgs`  *(new)*

List all orgs accessible to the current user.

**Auth:** Required (any role)

**Response `200`:**
```json
[
  { "id": "org_001", "name": "Root Org", "parent_id": null, "children": ["org_002"], "farms": [] },
  { "id": "org_002", "name": "Maharashtra Region", "parent_id": "org_001", "children": [], "farms": ["farm_001"] }
]
```

---

### `GET /api/org/<org_id>/detail`  *(new)*

Get details for a single org.

**Auth:** Required + must have org access

**Response `200`:**
```json
{ "id": "org_002", "name": "Maharashtra Region", "parent_id": "org_001", "children": [], "farms": ["farm_001"] }
```

---

### `GET /api/org/<org_id>/summary`

Get aggregated health summary for an org and all its descendant farms.

**Auth:** Required + org access

**Response `200`:**
```json
{
  "org_id": "org_002",
  "org_name": "Maharashtra Region",
  "farm_count": 3,
  "avg_health": 74.2,
  "issues_count": 8,
  "total_images": 240,
  "last_report_date": "2024-11-10T08:30:00",
  "farms": [ /* array of farm summaries */ ],
  "children": [ /* recursive org summaries */ ]
}
```

---

### `GET /api/org/<org_id>/orgs/list`

Lightweight list of orgs in this org's subtree (for dropdowns).

**Auth:** Required + org access

**Response `200`:** `[{ "id", "name", "parent_id" }]`

---

### `GET /api/org/<org_id>/farms/list`

Lightweight list of farms in this org's subtree (for dropdowns).

**Auth:** Required + org access

**Response `200`:** `[{ "id", "name", "org_ids" }]`

---

## Admin Endpoints

All admin endpoints require `admin` role unless noted.

### `GET /api/admin/orgs`

Full org list with health summaries and user counts.

**Response `200`:**
```json
[
  { "id": "org_001", "name": "Root Org", "parent_id": null, "farm_count": 5,
    "avg_health": 76.0, "issues_count": 4, "last_report_date": "...", "user_count": 3 }
]
```

---

### `POST /api/admin/orgs`

Create a new organization.

**Request body:** `{ "name": "New Region", "parent_id": "org_001" }` (`parent_id` optional)

**Response `201`:** New org object

---

### `GET /api/admin/farms/list`

Lightweight list of all farms.

**Response `200`:** `[{ "id", "name", "org_ids" }]`

---

### `POST /api/admin/farms`

Create a new farm. Requires `admin` or `org_admin`.

**Request body:**
```json
{ "name": "New Farm", "org_ids": ["org_002"], "lat": 17.709, "lng": 78.423 }
```

`lat`/`lng` are optional. `org_id` (scalar) is accepted as a legacy alternative to `org_ids`.

**Response `201`:** New farm object

---

### `GET /api/admin/users`

List all users (without passwords).

**Response `200`:**
```json
[
  { "id": "u1", "username": "admin", "display_name": "Administrator",
    "role": "admin", "org_id": null, "farm_ids": [] }
]
```

---

### `POST /api/admin/users`

Create a new user.

**Request body:**
```json
{
  "username": "ravi",
  "password": "secret123",
  "role": "user",
  "display_name": "Ravi Kumar",
  "org_id": null,
  "farm_ids": ["farm_001", "farm_002"]
}
```

`role` must be `admin`, `org_admin`, or `user`. `display_name`, `org_id`, `farm_ids` are optional.

**Response `201`:** New user object (without password) | **Response `409`:** Username taken

---

### `PATCH /api/admin/users/<user_id>`

Update a user's display name and/or password.

**Request body:** `{ "display_name": "New Name", "password": "newpass" }` (both optional)

**Response `200`:** Updated user object (without password)

---

### `POST /api/admin/farms/<farm_id>/upload`

Upload a plant health analysis JSON report for a farm. Requires `admin` or `org_admin`.

**Request:** `multipart/form-data` with field `file` containing a `.json` file.

**Response `201`:** `{ "ok": true, "filename": "report_2024_11_10.json", "farm_id": "farm_001" }`

**Response `400`:** Not a `.json` file or invalid JSON | **Response `409`:** Filename already exists

---

### `GET /api/admin/orgs/list`

Lightweight list of all orgs (for dropdowns).

**Response `200`:** `[{ "id", "name", "parent_id" }]`

---

## Image Upload Endpoint

### `POST /api/upload/<session_id>`

Upload an image with GPS coordinates. The server groups uploads by a client-supplied `session_id` (UUID), creating a dedicated folder for each session. Calling the endpoint multiple times with the same `session_id` adds images to the existing folder and appends to the same GPS log.

**Auth:** Required (any role)

**Request:** `multipart/form-data`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | binary | yes | Image file |
| `lat` | float | yes | Latitude |
| `lng` | float | yes | Longitude |
| `alt` | float | no | Altitude in metres |

Supported image formats: `.jpg`, `.jpeg`, `.png`, `.heic`, `.heif`, `.webp`, `.tiff`, `.tif`, `.bmp`

**Response `201`:**
```json
{
  "ok": true,
  "session_id": "3f6e2a1b-4c5d-6e7f-8a9b-0c1d2e3f4a5b",
  "image_filename": "20260501_103045_123456_IMG_001.jpg",
  "gps": { "latitude": 17.709, "longitude": 78.423, "altitude": 631.3 }
}
```

**Error responses:**

| Code | Cause |
|------|-------|
| 400 | `session_id` is not a valid UUID |
| 400 | `lat` or `lng` missing or not a number |
| 400 | `alt` provided but not a number |
| 400 | No file in request, or unsupported file type |
| 401 | Not authenticated |

**Session folder structure on the server:**

```
data/uploads/<session_id>/
  20260501_103045_123456_IMG_001.jpg   ← image, prefixed with UTC timestamp
  20260501_103112_654321_IMG_002.jpg
  gps.jsonl                            ← one JSON line per upload
```

Each line in `gps.jsonl`:
```json
{"image_filename": "20260501_103045_123456_IMG_001.jpg", "latitude": 17.709, "longitude": 78.423, "altitude": 631.3, "timestamp": "2026-05-01T10:30:45.123456"}
```

---

## Data Models

### Plant Health Report (returned by `GET /api/data/<farm_id>/<filename>`)

```json
{
  "report_metadata": {
    "generated_at": "2024-11-10T08:30:00",
    "folder_path": "/path/to/images",
    "model_used": "qwen3-vl",
    "total_images": 137,
    "successful_analyses": 85,
    "status": "completed"
  },
  "images": [
    {
      "image_name": "IMG_6734.HEIC",
      "file_size_mb": 4.996,
      "image_dimensions": { "width": 4032, "height": 3024 },
      "timestamp": "2024-11-10T08:15:00",
      "gps_coordinates": {
        "latitude": 17.70973,
        "longitude": 78.42350,
        "altitude": 631.3
      },
      "camera": { "make": "Apple", "model": "iPhone 14 Pro Max" },
      "plant_health_analysis": {
        "health_score": 80.0,
        "health_status": "good",
        "issues_detected": "Minor leaf discoloration",
        "recommended_interventions": "Apply foliar spray",
        "visual_observations": "Mostly healthy plants with minor spots",
        "bounding_boxes": [
          {
            "plant_id": 1,
            "bbox": [120, 80, 400, 350],
            "confidence": 0.92,
            "plant_condition": "healthy",
            "notes": "Vigorous growth"
          }
        ],
        "processing_time_seconds": 73.95
      }
    }
  ]
}
```

### Health Score Scale

| Score | Status | Color |
|-------|--------|-------|
| 75–100 | `good` | Green |
| 65–74 | `fair` | Orange |
| 0–64 | `poor` | Red |
| null | `unknown` | Grey |

---

## Error Responses

All errors follow: `{ "error": "<message>" }`

| Code | Meaning |
|------|---------|
| 400 | Bad request / missing required field |
| 401 | Not authenticated |
| 403 | Authenticated but insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (duplicate resource) |
| 502 | Upstream service error (weather) |

---

## Android Integration Notes

1. **Cookie-based sessions**: Use `JavaNetCookieJar` with OkHttp so the `session` cookie is persisted across requests:
   ```kotlin
   val cookieJar = JavaNetCookieJar(CookieManager())
   val client = OkHttpClient.Builder().cookieJar(cookieJar).build()
   ```

2. **File upload**: Use `MultipartBody` for both `POST /api/upload/<session_id>` (image + GPS) and `POST /api/admin/farms/<farm_id>/upload` (JSON health reports).

3. **Suggested startup flow**:
   - Call `GET /api/me` → if 401, show login screen
   - On login success, use `user.role` to decide which screen to show:
     - `admin` → full dashboard
     - `org_admin` → org summary for `user.org_id`
     - `user` → farm list from `GET /api/farms`
