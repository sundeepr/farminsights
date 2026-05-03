# FarmInsights Data Model

> Status: **Draft** — schema refinement in progress. Not yet implemented.

---

## Entities

### Organization
Hierarchical. An org can have child orgs (via `parent_id`) and no direct farm ownership.

```json
{
  "id": "org_001",
  "name": "Maharashtra",
  "parent_id": "org_root"    
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Unique identifier |
| `name` | string | Display name |
| `parent_id` | string \| null | Parent org id; null for root org |

Children and farms are **computed** — not stored as arrays on the org.

---

### Group
A UI-level label an org admin creates to visually categorize farms within their org.
Has no effect on access control or hierarchy.

```json
{
  "id": "grp_001",
  "name": "North Block",
  "org_id": "org_001"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Unique identifier |
| `name` | string | Label shown in UI |
| `org_id` | string | Org this group belongs to |

---

### Farm
Standalone entity — no direct org reference. Org relationship is inferred through farmers.

```json
{
  "id": "farm_001",
  "name": "Nimgaon Farm",
  "group_id": "grp_001",
  "lat": 20.3211,
  "lng": 80.1898,
  "data_folder": "data/farm_001"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Unique identifier |
| `name` | string | Display name |
| `group_id` | string \| null | Optional UI group label |
| `lat` | number \| null | GPS latitude |
| `lng` | number \| null | GPS longitude |
| `data_folder` | string | Path to health report JSON files |

---

### User
Three roles with different access scopes.

```json
{
  "id": "u1",
  "username": "ravi",
  "display_name": "Ravi Kumar",
  "password": "plaintext",
  "role": "user",
  "org_id": "org_001",
  "farm_ids": ["farm_001", "farm_002"]
}
```

| Field | Type | Roles | Notes |
|-------|------|-------|-------|
| `id` | string | all | Unique identifier |
| `username` | string | all | Login name |
| `display_name` | string | all | UI display name |
| `password` | string | all | ⚠ Plaintext — change before production |
| `role` | string | all | `admin` \| `org_admin` \| `user` |
| `org_id` | string \| null | `org_admin`, `user` | Org the user belongs to |
| `farm_ids` | string[] | `user` | Farms the farmer is assigned to |

---

## Access Control

### Role → Access

| Role | Sees |
|------|------|
| `admin` | All orgs, all farms, all users |
| `org_admin` | Their org + all sub-orgs + all farms whose farmers belong to those orgs |
| `user` (farmer) | Only their own `farm_ids` |

### How org_admin farm access is computed
```
org_admin.org_id
  → get subtree of org IDs (org + all descendants via parent_id)
    → find all users where user.org_id ∈ subtree AND user.role == "user"
      → collect all farm_ids from those users (deduplicated)
        → return those farms
```

### How farmer org context is determined
Farmer has `org_id` directly — no lookup needed.

---

## Org Hierarchy Example

```
Sunrise Agri Group  (org_root, parent_id: null)
├── Maharashtra  (org_001, parent_id: org_root)
│   └── Gadchiroli District  (org_002, parent_id: org_001)
└── Telangana  (org_003, parent_id: org_root)
    └── Sangareddy District  (org_004, parent_id: org_003)
```

Farmers in `org_002` → their farms appear under Maharashtra AND Gadchiroli District for their respective org admins.

---

## Open Questions / TODO

- [ ] Should `password` be hashed before production?
- [ ] Can a farmer be assigned to farms across different orgs? (currently: No — `org_id` is single)
- [ ] Should `group_id` be validated against groups that belong to the farmer's org?
- [ ] Is `data_folder` auto-generated on farm creation, or manually set?
- [ ] Should farms have a `crop_type` field (used to inform Gemini analysis)?
