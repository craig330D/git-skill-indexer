"""Sentence-transformers wrapper — CPU-only embedding."""

import logging

import numpy as np

log = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cpu",
                 batch_size: int = 64):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            log.info("Loading embedding model: %s (device=%s)", self.model_name, self.device)
            self._model = SentenceTransformer(self.model_name, device=self.device)

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode a list of texts into vectors. Loads model on first call."""
        self._load_model()
        log.info("Encoding %d texts in batches of %d", len(texts), self.batch_size)
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
        )
        return vectors

    def unload(self):
        """Release model from memory."""
        if self._model is not None:
            del self._model
            self._model = None
            log.info("Embedding model unloaded")
