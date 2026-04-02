"""Tests for embedder module — requires sentence-transformers installed."""

import pytest


def test_encode_returns_correct_shape():
    """Encode a few texts and verify vector dimensions."""
    from src.embedder import Embedder

    emb = Embedder(model_name="all-MiniLM-L6-v2", device="cpu", batch_size=2)
    try:
        texts = ["hello world", "semantic search", "agent pattern"]
        vectors = emb.encode(texts)
        assert vectors.shape == (3, 384)
    finally:
        emb.unload()


def test_unload_releases_model():
    from src.embedder import Embedder

    emb = Embedder(model_name="all-MiniLM-L6-v2", device="cpu")
    emb.encode(["test"])
    assert emb._model is not None
    emb.unload()
    assert emb._model is None
