"""Orchestrator: clone -> chunk -> embed -> store."""

import logging
from pathlib import Path

from .chunker import chunk_repo
from .cloner import cleanup_clone, shallow_clone
from .embedder import Embedder
from .store import VectorStore

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, config: dict):
        self.config = config
        self.clone_dir = Path(config["indexer"]["clone_dir"])
        self.store = VectorStore(
            host=config["qdrant"]["host"],
            port=config["qdrant"]["port"],
            collection=config["qdrant"]["collection"],
            vector_size=config["qdrant"]["vector_size"],
        )
        self.embedder = Embedder(
            model_name=config["embedding"]["model"],
            device=config["embedding"]["device"],
            batch_size=config["embedding"]["batch_size"],
        )

    def index_repo(self, repo_meta: dict, force: bool = False) -> int:
        """Index a single repo: clone, chunk, embed, store. Returns chunk count."""
        repo_name = repo_meta["full_name"]

        if not force and self.store.repo_exists(repo_name):
            # Delete existing chunks before re-indexing
            self.store.delete_repo(repo_name)

        target = self.clone_dir / repo_name.replace("/", "_")
        try:
            clone_url = repo_meta.get("clone_url") or repo_meta["html_url"] + ".git"
            shallow_clone(clone_url, target)

            chunks = chunk_repo(target, repo_meta, self.config["indexer"])
            if not chunks:
                log.warning("No chunks extracted from %s", repo_name)
                return 0

            texts = [c["text"] for c in chunks]
            vectors = self.embedder.encode(texts)

            self.store.upsert_chunks(chunks, vectors.tolist())
            log.info("Indexed %s: %d chunks", repo_name, len(chunks))
            return len(chunks)

        finally:
            cleanup_clone(target)

    def index_url(self, url: str) -> int:
        """Index a repo from a URL (not necessarily starred)."""
        # Extract owner/repo from URL
        parts = url.rstrip("/").split("/")
        if len(parts) >= 2:
            full_name = f"{parts[-2]}/{parts[-1]}"
        else:
            full_name = parts[-1]

        repo_meta = {
            "full_name": full_name,
            "html_url": url,
            "clone_url": url + ".git" if not url.endswith(".git") else url,
            "description": "",
            "language": "",
            "topics": [],
        }
        return self.index_repo(repo_meta, force=True)

    def remove_repo(self, repo_name: str):
        """Remove a repo from the index."""
        self.store.delete_repo(repo_name)
        log.info("Removed %s from index", repo_name)

    def unload(self):
        """Release embedding model from memory."""
        self.embedder.unload()
