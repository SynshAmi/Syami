from typing import Any


class SentenceTransformerEmbedder:

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        model: Any | None = None,
    ):
        self._model_name = model_name
        self._model = model

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)

        return self._model

    def embed_chunks(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()

        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        return [vector.tolist() for vector in embeddings]

    def embed_text(
        self,
        text: str,
    ) -> list[float]:
        if not text:
            return []

        embeddings = self.embed_chunks([text])
        return embeddings[0] if embeddings else []

