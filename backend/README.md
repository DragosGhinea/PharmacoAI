# PharmacoAI Backend (FastAPI)

JSON-based backend for user management with admin-controlled tiers and message limits.

## Stack

- FastAPI
- Uvicorn
- Local JSON persistence (`data/users.json`)

## Roles

- `admin`: full CRUD access for all users
- `pharmacist`: read own profile and simulate own AI messages

## Tiers

- `free`: 50 messages/month, `basic-assistant`
- `pro`: 500 messages/month, `basic-assistant`, `clinical-analyst`
- `ultimate`: 2000 messages/month, `basic-assistant`, `clinical-analyst`, `strategic-advisor`

## Local Run

From repository root:

```bash
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Swagger UI:

- http://127.0.0.1:8000/docs

## Auth Placeholder

Use header `X-User-Id` for each protected endpoint.

Default seeded admin user id: `admin-0001`

## API Summary

- `GET /health`
- `GET /tiers`
- `GET /users` (admin)
- `GET /users/me`
- `GET /users/{user_id}` (admin or self)
- `POST /users` (admin)
- `PUT /users/{user_id}` (admin)
- `DELETE /users/{user_id}` (admin)
- `POST /users/{user_id}/messages` (admin or self)

## Example Create User

```bash
curl -X POST http://127.0.0.1:8000/users \
  -H "Content-Type: application/json" \
  -H "X-User-Id: admin-0001" \
  -d "{\"email\":\"ana@pharmacoai.local\",\"full_name\":\"Ana Popescu\",\"tier\":\"pro\",\"role\":\"pharmacist\",\"is_active\":true}"
```

## MCP Server (Medication V1)

An additive MCP server is available under `backend/mcp` and runs independently from the FastAPI REST API.

### Transport

- Streamable HTTP (stateless, JSON response mode)
- Default endpoint: `http://127.0.0.1:8010/mcp`

### Run MCP Server

From repository root:

```bash
.venv\Scripts\python.exe -m backend.mcp
```

Environment variables:

- `MCP_HOST` (default `127.0.0.1`)
- `MCP_PORT` (default `8010`)
- `MCP_RATE_LIMIT_PER_MINUTE` (default `60`, per caller and capability)
- `MCP_ENABLE_OPENFDA` (default `1`, enables openFDA live label lookups with mock fallback)
- `MCP_OPENFDA_CACHE_TTL_SECONDS` (default `300`, in-memory TTL for openFDA lookups)
- `MCP_SERVER_URL` (used by smoke client, default `http://127.0.0.1:8010/mcp`)

### Tools (v1)

All tools/resources/prompts expose explicit `title` and `description` metadata so MCP clients can reason about capability intent during discovery.

- `normalize_medication_name`
- `search_medication_facts`
- `find_similar_medications`
- `check_contraindications`
- `check_interactions`
- `explain_for_patient`
- `collect_missing_context`

### Resources (v1)

- `drug://label/{drug_id}`
- `drug://ingredients/{drug_id}`
- `drug://classes/{drug_id}`
- `drug://contraindications/{drug_id}`
- `drug://interactions/{drug_id}`
- `drug://patient-leaflet/{drug_id}`
- `drug://evidence/{drug_id}/{section}`

### Prompts (v1)

- `medication_summary`
- `patient_explanation`
- `interaction_review`
- `contraindication_review`
- `compare_medications`
- `red_flag_review`

### Safety and Operations Notes

- High-risk checks return warnings when critical context is missing; they do not hard-stop in v1.
- Safety-oriented outputs include evidence references.
- Every capability invocation emits a basic audit log event.
- Data is mock-safe for v1 and intended for development workflows only.

### External Data Source

The MCP server now uses openFDA drug label data as the first live source for medication normalization/facts (with graceful fallback to local mock records when unavailable).

### End-to-End Smoke Test

Start MCP server:

```bash
.venv\Scripts\python.exe -m backend.mcp
```

In another terminal, run the MCP client smoke script:

```bash
.venv\Scripts\python.exe backend/mcp/scripts/mcp_smoke_client.py
```
