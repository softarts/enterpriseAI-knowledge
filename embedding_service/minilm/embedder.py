"""MiniLM implementation of the common Embedder interface."""

from typing import List, Sequence


class MiniLMEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", dimension: int = 384, normalize_embeddings: bool = True, batch_size: int = 32, model: object = None, **_: object):
        self.model_name, self.dimension = model_name, dimension
        self.normalize_embeddings, self.batch_size = normalize_embeddings, batch_size
        self._model = model

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts: return []
        values = self._get_model().encode(list(texts), batch_size=self.batch_size,
            normalize_embeddings=self.normalize_embeddings, show_progress_bar=False)
        return [value.tolist() if hasattr(value, "tolist") else list(value) for value in values]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
