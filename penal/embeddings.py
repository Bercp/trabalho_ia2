from functools import lru_cache

from fastembed import TextEmbedding

from penal.config import ROOT, settings


@lru_cache
def embedder() -> TextEmbedding:
    return TextEmbedding(
        model_name=settings().embedding_model,
        cache_dir=str(ROOT / "data/models"),
        threads=4,
    )


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in embedder().passage_embed(texts, batch_size=32)]


def embed_query(text: str) -> list[float]:
    return next(embedder().query_embed(text)).tolist()
