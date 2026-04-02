# git-skill-indexer

## Branch
- Work on `development` branch

## Architecture
- Indexes GitHub starred repos into Qdrant vector DB for semantic search
- CPU-only embedding with sentence-transformers (all-MiniLM-L6-v2)
- FastAPI server with MCP-compatible endpoint on port 8420
- Nightly sync via systemd timer

## Key paths
- Source: `src/`
- Config: `config.yaml`
- Qdrant: Docker container on port 6333

## Commands
- `git-skill-indexer sync` — sync starred repos
- `git-skill-indexer query "..."` — semantic search
- `git-skill-indexer index <url>` — index a specific repo
- `uvicorn src.server:app --port 8420` — run API server

## Rules
- Never use GPU for embedding — CPU only
- Clone dir is ephemeral — clean up after indexing
- GITHUB_PAT comes from env var, never hardcode tokens
