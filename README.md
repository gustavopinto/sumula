# Sumula

FAPESP Curriculum Summary builder from multiple sources: file uploads (PDF, XLS/XLSX, TXT, MD) and URLs (Lattes, ORCID, DBLP, Google Scholar, Web of Science, personal site). Output is FAPESP-format Markdown; optional async email delivery via MailerSend.

## Features

- **Inputs**: PDF, XLS/XLSX, TXT, MD files; Lattes, ORCID, DBLP, Google Scholar, Web of Science, personal site URLs; BibTeX paste for Scholar (MVP).
- **Processing**: Text extraction and curation to structured TXT; LLM used only on curated text to generate the summary.
- **Output**: FAPESP-formatted curriculum summary in Markdown.
- **Email**: Optional async sending via MailerSend (no sign-up required for MVP).

## Requirements

- Python 3.11+
- Docker (PostgreSQL 16, Redis 7)
- OpenAI API key

## Quick start

1. **Clone and enter the repo**
   ```bash
   git clone git@github.com:gustavopinto/sumula.git && cd sumula
   ```

2. **Create virtualenv and install**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your OPENAI_API_KEY, MailerSend SMTP, etc.
   ```

4. **Start dependencies**
   ```bash
   docker compose up -d
   ```

5. **Run the app**
   ```bash
   ./run.sh
   ```

   This starts the API (uvicorn) and the background worker (arq). Use `./stop.sh` to stop them.

## Configuration

See `.env.example` for all variables. Main ones:

- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_MAX_TOKENS` — LLM
- `DATABASE_URL` — PostgreSQL (async)
- `REDIS_URL` — Redis (for arq)
- `MAX_UPLOAD_MB`, `MAX_FILES` — Upload limits
- `WORKDIR_PATH` — Directory for job files
- MailerSend: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_DEFAULT_SENDER`, `MAIL_DEFAULT_SENDER_NAME`

## Project structure

- `app/` — FastAPI app, routes, extractors, worker, config
- `migrations/` — Alembic migrations
- `run.sh` / `stop.sh` — Start/stop API and worker
- `spec.md` — Full specification (in Portuguese)

## License

See repository for license information.
