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
- `GET /agents`
- `GET /agents/{agent_id}`
- `POST /agents/{agent_id}/chat`
- `POST /agents/handoff`
- `GET /agents/conversations/{conversation_id}`

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

## Multi-Agent Backend Interface

The backend now includes a configurable multi-agent interface with pluggable providers:

- `gemini` provider (Google Gemini API)
- `api` provider (generic REST chat-completion style endpoint)

The default architecture follows a retrieval-first medication pipeline:

1. Normalize medication names with RxNorm (RxNav approximate matching).
2. Retrieve grounding evidence from openFDA label sections.
3. Retrieve DailyMed SPL references for additional source linking.
4. Route grounded context to agents for clinician-style and patient-style outputs.

### Agent Definitions

Default agent definitions are in `backend/app/agents_catalog.py` and include the medication-oriented agents discussed previously:

- medication-info-agent
- layman-translator-agent
- safety-contraindication-agent

You can override definitions via environment variable:

- `PHARMACOAI_AGENTS_CONFIG` (path to JSON list of agent definitions)

### Provider Configuration

Gemini-backed agents require:

- `GEMINI_API_KEY_1`
- `GEMINI_API_KEY_2`
- `GEMINI_API_KEY_3` (used by layman-translator-agent)

Generic API-backed agents require:

- `PLATFORM_AGENT_API_KEY`
- `base_url` configured per agent definition

Note: In the current default catalog, all three agents are Gemini-backed, so `PLATFORM_AGENT_API_KEY` is optional unless you add API-provider agents.

You can place these values in repository root `.env`.

### Agent Communication Endpoints

All endpoints use the existing `X-User-Id` auth header.

- `GET /agents`: list active configured agents
- `GET /agents/{agent_id}`: get one agent definition
- `POST /agents/{agent_id}/chat`: send a user message to an agent and optional handoff chain
- `POST /agents/handoff`: send one agent's message to another agent
- `GET /agents/conversations/{conversation_id}`: fetch conversation state and message history

`POST /agents/{agent_id}/chat` accepts:

- `message` (required)
- `conversation_id` (optional)
- `handoff_to` (optional list of agent IDs)
- `metadata.medication_name` (optional, strongly recommended for better grounding)

Agent chat responses now include:

- `clinician_summary`
- `patient_summary`
- `evidence_snippets`
- `source_links`
- per-turn metadata in `turns`

### Additional Environment Variables

- `DRUG_SOURCES_CACHE_TTL_SECONDS` (default `300`, cache TTL for RxNorm/openFDA/DailyMed retrieval context)
