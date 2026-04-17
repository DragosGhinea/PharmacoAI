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
