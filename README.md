# PharmacoAI

University Project - Startup.

## Project Structure

- `frontend/`: React + Vite UI and landing page.
- `backend/`: FastAPI API with JSON storage for user CRUD and tier logic.

## Run All Services (PowerShell)

From repository root in PowerShell:

```powershell
.\start_all.ps1
```

This starts backend API, MCP server, and frontend dev server. Press `Ctrl+C` to stop all.

Both backend and MCP automatically load environment variables from repository root `.env` (if present).

## Backend Quick Start

Run from repository root:

```bash
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

The backend auto-loads variables from repository root `.env`.

API docs:

- `http://127.0.0.1:8000/docs`

## MCP Quick Start

Run from repository root:

```bash
.venv\Scripts\python.exe -m backend.mcp
```

The MCP server auto-loads variables from repository root `.env`.

MCP endpoint:

- `http://127.0.0.1:8010/mcp`

## Frontend Quick Start

Run from `frontend/`:

```bash
npm install
npm run dev
```

To connect frontend requests to backend, set:

- `VITE_API_BASE_URL=http://127.0.0.1:8000`

The backend integration helper is in `frontend/src/api/usersApi.js`, and a styled admin panel component is in `frontend/src/components/AdminUsersPanel.jsx`.
