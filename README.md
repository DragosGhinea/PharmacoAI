# PharmacoAI

University Project - Startup.

## Project Structure

- `frontend/`: React + Vite UI and landing page.
- `backend/`: FastAPI API with JSON storage for user CRUD and tier logic.

## Backend Quick Start

Run from repository root:

```bash
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

API docs:

- `http://127.0.0.1:8000/docs`

## Frontend Quick Start

Run from `frontend/`:

```bash
npm install
npm run dev
```

To connect frontend requests to backend, set:

- `VITE_API_BASE_URL=http://127.0.0.1:8000`

The backend integration helper is in `frontend/src/api/usersApi.js`, and a styled admin panel component is in `frontend/src/components/AdminUsersPanel.jsx`.
