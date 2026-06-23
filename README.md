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

## status

phase 0 scaffolding. not yet functional end-to-end.
