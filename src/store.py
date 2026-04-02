"""Qdrant client wrapper — vector storage operations."""

import hashlib
import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

log = logging.getLogger(__name__)


def _deterministic_id(repo_name: str, file_path: str, line_start: int) -> str:
    """Generate a deterministic UUID from chunk identity."""
    key = f"{repo_name}:{file_path}:{line_start}"
    return str(uuid.UUID(hashlib.md5(key.encode()).hexdigest()))


class VectorStore:
    def __init__(self, host: str = "localhost", port: int = 6333,
                 collection: str = "git-skills", vector_size: int = 384):
        self.client = QdrantClient(host=host, port=port)
        self.collection = collection
        self.vector_size = vector_size
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )
            log.info("Created collection '%s'", self.collection)

    def upsert_chunks(self, chunks: list[dict], vectors: list[list[float]]):
        """Batch upsert chunks with their vectors."""
        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = _deterministic_id(
                chunk["repo_name"], chunk["file_path"], chunk["line_start"]
            )
            payload = {k: v for k, v in chunk.items() if k != "text"}
            payload["text"] = chunk["text"][:5000]  # Truncate very long text in payload

            points.append(PointStruct(
                id=point_id,
                vector=vector if isinstance(vector, list) else vector.tolist(),
                payload=payload,
            ))

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upsert(collection_name=self.collection, points=batch)

        log.info("Upserted %d chunks to '%s'", len(points), self.collection)

    def delete_repo(self, repo_name: str):
        """Remove all points for a repo."""
        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(key="repo_name", match=MatchValue(value=repo_name))]
            ),
        )
        log.info("Deleted all chunks for %s", repo_name)

    def search(self, query_vector: list[float], top_k: int = 10,
               filters: dict | None = None) -> list[dict]:
        """Semantic search with optional metadata filters."""
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
            qdrant_filter = Filter(must=conditions)

        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
        )

        return [
            {
                "score": hit.score,
                **hit.payload,
            }
            for hit in results
        ]

    def repo_exists(self, repo_name: str) -> bool:
        """Check if a repo has any chunks in the collection."""
        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="repo_name", match=MatchValue(value=repo_name))]
            ),
            limit=1,
        )
        return len(results[0]) > 0

    def get_indexed_repos(self) -> list[str]:
        """List all unique repo names in the collection."""
        repos = set()
        offset = None

        while True:
            results, offset = self.client.scroll(
                collection_name=self.collection,
                limit=100,
                offset=offset,
                with_payload=["repo_name"],
            )
            for point in results:
                repos.add(point.payload["repo_name"])
            if offset is None:
                break

        return sorted(repos)

    def get_stats(self) -> dict:
        """Get collection statistics."""
        info = self.client.get_collection(self.collection)
        repos = self.get_indexed_repos()
        return {
            "total_chunks": info.points_count,
            "total_repos": len(repos),
            "vector_size": info.config.params.vectors.size,
            "status": info.status.value,
        }
