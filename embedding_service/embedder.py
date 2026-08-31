import logging
from typing import List, Optional
from sentence_transformers import SentenceTransformer

from embedding_service.config import EMBEDDING_MODEL_NAME, EMBEDDING_DIMENSION

logger = logging.getLogger(__name__)


class LocalEmbedder:
    """
    Local embedding generator using sentence-transformers.
    Runs completely offline / locally without external databases or services.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self.dimension = EMBEDDING_DIMENSION
        self._model: Optional[SentenceTransformer] = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("Loading embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate normalized embeddings for a list of texts.
        """
        if not texts:
            return []
        model = self._get_model()
        # normalize_embeddings=True makes cosine similarity equal to dot product
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]

    def embed_query(self, query: str) -> List[float]:
        """
        Generate normalized embedding for a single query string.
        """
        embs = self.embed_texts([query])
        return embs[0] if embs else []
