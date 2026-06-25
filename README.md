# kairo

an ai assistant that remembers your anime taste.

chatgpt/claude-style chat ui + anilist integration + anime-specific memory. the product
value is `your context + llm reasoning`, not a recommendation engine.

see `plan.md` for architecture and `todo.md` for the implementation checklist.

## stack

- backend: fastapi (python 3.11+), sqlalchemy 2.0 async, postgres 16
- frontend: next.js 15, typescript, tailwind
- llm: provider-agnostic (openrouter default, plus openai / anthropic / ollama)

## self-host (dev)

prerequisites: docker, python 3.11+, node 20+.

1. copy env templates and fill them in:
   ```
   cp backend/.env.example backend/.env
   ```
   generate the two secrets:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FERNET_KEY
   python -c "import secrets; print(secrets.token_urlsafe(32))"                                  # SESSION_SECRET
   ```
   register an AniList api client at https://anilist.co/settings/developer and set
   `ANILIST_CLIENT_ID` / `ANILIST_CLIENT_SECRET` / `ANILIST_REDIRECT_URI`.

2. start postgres + backend:
   ```
   docker compose up --build
   ```

3. run migrations (first boot):
   ```
   docker compose exec backend alembic upgrade head
   ```

4. health check: http://localhost:8000/health

## prod deploy

prerequisites: docker, a domain/reverse proxy (nginx/caddy), anilist oauth app.

1. copy and fill in secrets:
   ```
   cp backend/.env.example backend/.env
   ```
   generate required secrets:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY
   python -c "import secrets; print(secrets.token_urlsafe(32))"                               # SESSION_SECRET
   ```
   set `DATABASE_URL` to point at your postgres host (or leave as-is to use the compose db).

2. build and start:
   ```
   docker compose -f docker-compose.prod.yml up -d --build
   ```
   migrations run automatically before uvicorn starts. single worker is enforced (rate-limit
   buckets are in-process; multiple workers would multiply the effective limits).

3. health check:
   ```
   curl http://localhost:8000/health
   ```
   `/docs` and `/openapi.json` are hidden in production (`ENVIRONMENT=production`).

4. reverse proxy: point your proxy at `localhost:8000`. set `FRONTEND_ORIGIN` to your frontend
   domain in `.env` before starting.

## status

phase 4 complete. functional end-to-end: auth, anilist sync, taste profiling, conversation
with context-aware LLM, structured logging, rate limiting, provider abstraction (openrouter /
ollama), 31 passing tests.
