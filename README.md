# React DocChat

A small React documentation assistant built as two local applications in one workspace:

- `web/` — Next.js UI and backend-for-frontend proxy
- `api/` — FastAPI, LangChain, and the existing Chroma collection

The answer pipeline retrieves React documentation, asks a configurable chat model for a grounded Markdown answer, and returns the source excerpts used to create it. The UI streams progress events, renders highlighted code, and turns React docs-style `<Sandpack>` examples into editable previews. The browser keeps the 15 most recent questions, while Next.js caches matching answers with weekly stale-while-revalidate behavior. Removing a history entry also invalidates its cached answer.

## Run locally

1. Copy the root environment template and add your OpenAI and LangSmith credentials:

   ```bash
   cp .env.sample .env
   ```

   `CHROMA_PATH` and `REACT_DEV_ROOT` may be absolute, or relative to this repository's
   root. `ALLOWED_ORIGINS` is a comma-separated list; its default permits both localhost
   forms used by the web app.

2. Copy `web/.env.sample` to `web/.env.local` if the API does not run at `http://127.0.0.1:8000`.
3. Start the API:

   ```bash
   cd api
   uv sync --dev
   uv run fastapi dev app/main.py --port 8000
   ```

4. Start the web app in another terminal:

   ```bash
   cd web
   pnpm install
   pnpm dev
   ```

Open [http://localhost:3000](http://localhost:3000).

## Data

The existing Chroma collection is copied to `data/embeddings`. The directory is local-only and
Git-ignored because it contains generated vector data. `CHROMA_PATH=data/embeddings` selects it
by default.

`REACT_DEV_ROOT` points at the `src/content` directory in a local `react.dev` checkout. The
default, `../gh/react.dev/src/content`, matches this workspace layout; update it when the docs
repository lives elsewhere. The API derives the `reference`, `learn`, and `blog` source paths
from that root.

Re-index the reference, learn, and blog Markdown with:

```bash
cd api
uv run python -m app.ingest
```

## Checks

```bash
cd api && uv run pytest && uv run ruff check .
cd web && pnpm test && pnpm lint && pnpm build
```
