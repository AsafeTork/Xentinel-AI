# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

- **Build Docker images**:
  ```bash
  docker compose build
  ```
- **Start the application locally** (Docker Compose will launch the web service and the worker):
  ```bash
  docker compose up --detach
  ```
- **Run database migrations** (inside the `web` container):
  ```bash
  docker compose exec web flask db upgrade
  ```
- **Run the full test suite**:
  ```bash
  pytest -q
  ```
- **Run a single test** (replace `<path>::<test_name>` with the desired test):
  ```bash
  pytest -q <path>::<test_name>
  # Example:
  pytest -q tests/test_auth.py::test_login_success
  ```
- **Lint / static analysis** (project uses `flake8` if installed):
  ```bash
  flake8 .
  ```

## High‑Level Architecture

The system is a Flask‑based web application that follows a clear separation of concerns:

```
+-------------------+      +-------------------+      +-------------------+
|   HTTP API (Flask)│<----▶|   Routes (nexus/routes)│   │   Controllers/   │
+-------------------+      +-------------------+      |   Services (nexus/services)   |
        ▲                               │                           +-------------------+
        │                               ▼
        │                     +-------------------+   
        │                     |   Business Logic  │   
        │                     +-------------------+   
        │                               │
        ▼                               ▼
   +----------+                 +----------+   
   | Models   │                 |  Cache   │   
   | (SQLAlchemy)│               | (Redis)  │   
   +----------+                 +----------+   
        │                               │
        ▼                               ▼
   +-------------------+        +-------------------+
   | PostgreSQL DB     │        | RQ Worker (async) │
   +-------------------+        +-------------------+
```

- **`app.py`** creates the Flask app and registers Blueprints from `nexus/routes`.
- **`nexus/models.py`** defines SQLAlchemy ORM models (users, sites, audits, etc.).
- **`nexus/routes/*`** contain the HTTP endpoints (auth, admin, audit, billing, dashboard, etc.).
- **`nexus/services/*`** implement the core business logic: decision engine, audit engine, revenue impact calculations, policy enforcement, LLM integrations, caching, and queue management.
- **Redis + RQ** powers background processing. Workers are started via the `worker.py` script and consume jobs enqueued by the services layer.
- **Docker** composes three main containers: `web` (Flask), `worker` (RQ), and `redis` (message broker). PostgreSQL runs as an external service (local Docker Compose or managed cloud).
- **External integrations** include Stripe for billing, OpenAI‑compatible LLM endpoints, and optional Google/OAuth for authentication.
- **Safety & Policy Engine** gates all automatic actions, configurable via environment variables (e.g., `POLICY_DEFAULT_MAX_RISK_LEVEL`).

## Useful Entry Points
- **`nexus/cli.py`** – command‑line utilities for admin tasks.
- **`scripts/validate_migrations.py`** – sanity‑check Alembic migrations.
- **`tests/`** – pytest suite covering auth flow and decision engine.

When adding new functionality, extend the appropriate `services` module, expose a route in `nexus/routes`, and write corresponding tests.
