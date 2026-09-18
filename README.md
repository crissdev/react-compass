# React Compass

A small React documentation assistant built as two applications in one workspace:

- `web/` — Next.js UI and backend-for-frontend proxy
- `api/` — FastAPI, LangChain, and Chroma (local or Chroma Cloud)

The answer pipeline classifies every uncached question for React relevance and prompt-injection attempts. React questions continue through retrieval and grounded answer generation; other inputs receive a fixed scope notice without running RAG. The UI streams progress events, renders highlighted code, and turns React docs-style `<Sandpack>` examples into editable previews. The browser keeps the 15 most recent questions. Next.js caches successful React answers for a week and immediately invalidates no-match results and scope notices, so only grounded answers are reused. Removing a history entry also invalidates its cached React answer.

## How it works

![React Compass architecture, from documentation ingestion through retrieval and answer rendering](docs/react-compass-architecture.png)

## Run locally

1. Initialize the React documentation submodule:

   ```bash
   git submodule update --init --recursive
   ```

2. Copy the API environment template and add your OpenAI and LangSmith credentials:

   ```bash
   cp api/.env.sample api/.env
   ```

   The API is expected to run with `api/` as its working directory. `CHROMA_PATH` and
   `REACT_DEV_ROOT` may be absolute, or relative to that directory. `ALLOWED_ORIGINS` is
   a comma-separated list. `EMBEDDING_MODEL` selects the OpenAI embedding model used by both
   ingestion and retrieval; changing it requires rebuilding the Chroma database.

3. Copy `web/.env.sample` to `web/.env.local` if the API does not run at `http://127.0.0.1:8000`.
4. Start the API:

   ```bash
   cd api
   uv sync --dev
   uv run fastapi dev app/main.py --port 8000
   ```

5. Start the web app in another terminal:

   ```bash
   cd web
   pnpm install
   pnpm dev
   ```

Open [http://localhost:3000](http://localhost:3000).

## Data

The generated Chroma collection is stored in `data/embeddings`. The directory is local-only and
Git-ignored because it contains generated vector data. From the `api/` working directory,
`CHROMA_PATH=../data/embeddings` selects it. Ingestion indexes sections beginning at the first
level-two heading and intentionally ignores the introductory content before it.

For production, configure `CHROMA_API_KEY`, `CHROMA_TENANT`, and `CHROMA_DATABASE`. The API then
uses Chroma Cloud instead of `CHROMA_PATH`; the collection name remains `react-docs` unless
`CHROMA_COLLECTION` is overridden.

The `react.dev` submodule provides the documentation source. From the `api/` working directory,
`REACT_DEV_ROOT=../react.dev/src/content` selects its content directory. The API derives the
`reference`, `learn`, and `blog` source paths from that root.

Re-index the reference, learn, and blog Markdown with:

```bash
cd api
uv run python -m app.ingest
```

## Deploy to Vercel

The root `vercel.json` deploys `web/` and `api/` as Vercel Services. The Next.js service is public;
FastAPI stays private and is reached through the `API_BASE_URL` service binding.

Set the Vercel project's framework preset to **Services**, then configure these production secrets:

- `OPENAI_API_KEY`
- `CHROMA_API_KEY`
- `CHROMA_TENANT`

`CHROMA_DATABASE` defaults to `react-docs`. LangSmith remains optional; configure
`LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and `LANGSMITH_TRACING=true` to enable tracing.

## Checks

```bash
cd api && uv run pytest && uv run ruff check .
cd web && pnpm test && pnpm lint && pnpm build
```
