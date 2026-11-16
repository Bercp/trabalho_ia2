import hashlib
import json
import math
import re
from collections import Counter, defaultdict

import numpy as np

import chromadb
from chromadb.config import Settings as ChromaSettings

from penal.config import ROOT, settings
from penal.guardrails import normalize, unaccent
from penal.schemas import Chunk, DocumentResult, SearchResult, Topic, TopicsResult


def index_signature() -> str:
    c = settings()
    return hashlib.sha256(f'v1|{c.embedding_model}|{c.chunk_size}|{c.chunk_overlap}'.encode()).hexdigest()


def connect():
    return chromadb.PersistentClient(path=str(ROOT / "data/chroma"), settings=ChromaSettings(anonymized_telemetry=False))


# Termos de enquadramento tendem a dominar embeddings de perguntas jurídicas.
# Os termos de conteúdo (ex.: legítima defesa) permanecem no foco da consulta.
QUERY_STOP = set("a o as os um uma uns umas de da do das dos e em no na nos nas ao aos para por com que qual quais como quando onde porque se sua seu suas seus esse essa este esta isso eu voce ele ela sobre entre segundo sao ser foi seja tem ha pelo pela mais pode podem seria saber explique explicar diferenca conceito conceitos codigo codigos penal penais brasileiro brasileira legislacao lei leis artigo art estabelece preve previsto prevê apenas documento documentos base acervo resposta pergunta pena penas crime crimes".split())
QUERY_STOP.update({"diz", "dispoe", "define", "significa", "entende", "seguintes"})


def query_terms(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", unaccent(text)) if (len(word) >= 3 or word.isdigit()) and word not in QUERY_STOP]


class LexicalIndex:
    """BM25 pequeno e determinístico para complementar a recuperação vetorial."""
    def __init__(self, rows):
        self.rows = rows
        self.postings = defaultdict(dict)
        self.lengths = {}
        for id_, row in rows.items():
            counts = Counter(query_terms(row["text"]))
            self.lengths[id_] = sum(counts.values())
            for term, freq in counts.items():
                self.postings[term][id_] = freq
        self.average = sum(self.lengths.values()) / max(1, len(rows))

    def search(self, terms: list[str], topic: str | None):
        scores = defaultdict(float)
        n = len(self.rows)
        for term in set(terms):
            posting = self.postings.get(term, {})
            idf = math.log(1 + (n - len(posting) + 0.5) / (len(posting) + 0.5))
            for id_, frequency in posting.items():
                if topic and self.rows[id_]["meta"]["topic_key"] != topic:
                    continue
                length_norm = 1.5 * (1 - 0.75 + 0.75 * self.lengths[id_] / max(1, self.average))
                scores[id_] += idf * frequency * 2.5 / (frequency + length_norm)
        return [id_ for id_, _ in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:60]]


class KnowledgeStore:
    def __init__(self):
        self.index = json.loads((ROOT / "data/processed/index.json").read_text(encoding="utf-8"))
        if self.index["signature"] != index_signature():
            raise ValueError("Configuração de embeddings/chunks mudou. Execute python -m penal.ingest.")
        self.collection = connect().get_collection(self.index["collection"], embedding_function=None)
        self.documents = {d["document_id"]: d for d in self.index["documents"]}
        all_rows = self.collection.get(include=["documents", "metadatas"])
        self.rows = {id_: {"text": text, "meta": meta} for id_, text, meta in zip(all_rows["ids"], all_rows["documents"], all_rows["metadatas"])}
        self.lexical = LexicalIndex(self.rows)

    def search(self, query: str, top_k: int = 5, topic_key: str | None = None) -> SearchResult:
        from penal.embeddings import embed_query

        kwargs = {"where": {"topic_key": topic_key}} if topic_key else {}
        terms = query_terms(query)
        focus = " ".join(terms) or query
        article_numbers = re.findall(r"\bart(?:igo)?\.?\s*(\d+(?:-[a-z])?)", unaccent(query))
        article_patterns = [re.compile(r"\bart\.?\s*" + re.escape(number) + r"(?:[º°o])?(?![\da-z]|-[a-z])") for number in article_numbers]
        article_ids = {id_ for id_, row in self.rows.items() if article_patterns
                       and (not topic_key or row["meta"]["topic_key"] == topic_key)
                       and any(pattern.search(unaccent(row["text"])) for pattern in article_patterns)}
        if article_numbers:
            focus = "artigo " + focus
        vector = embed_query(focus)
        result = self.collection.query(query_embeddings=[vector], n_results=min(60, self.collection.count()), include=["distances"], **kwargs)
        ranking = defaultdict(float)
        similarities = {}
        for rank, (id_, distance) in enumerate(zip(result["ids"][0], result["distances"][0]), 1):
            ranking[id_] += 1 / (40 + rank)
            similarities[id_] = max(-1.0, min(1.0, 1 - distance))
        lexical_ids = self.lexical.search(terms, topic_key)
        for rank, id_ in enumerate(lexical_ids, 1):
            ranking[id_] += 1.5 / (40 + rank)
        for id_ in article_ids:
            ranking[id_] += 2 / 40
        missing = [id_ for id_ in set(lexical_ids) | article_ids if id_ not in similarities]
        if missing:
            extra = self.collection.get(ids=missing, include=["embeddings"])
            q = np.asarray(vector)
            for id_, emb in zip(extra["ids"], extra["embeddings"]):
                similarities[id_] = float(np.dot(q, emb) / max(1e-9, np.linalg.norm(q) * np.linalg.norm(emb)))
        hits, seen = [], set()
        for id_ in sorted(ranking, key=ranking.get, reverse=True):
            if article_numbers and id_ not in article_ids:
                continue
            row, similarity = self.rows[id_], similarities[id_]
            key = normalize(row["text"])
            # Termos centrais ausentes + baixa similaridade: não força uma resposta.
            matches = set(terms) & set(query_terms(row["text"]))
            exact_article = id_ in article_ids
            if (similarity < settings().min_similarity and not exact_article) or key in seen or (terms and not matches and similarity < 0.8 and not exact_article):
                continue
            seen.add(key)
            hits.append(Chunk(chunk_id=id_, text=row["text"], similarity=round(similarity, 4), retrieval_method="article_match" if exact_article else "hybrid", **row["meta"]))
            if len(hits) == top_k:
                break
        return SearchResult(query=query, chunks=hits, sufficient=bool(hits), threshold=settings().min_similarity)

    def get_document(self, document_id: str, page: int = 1) -> DocumentResult:
        if document_id not in self.documents:
            raise ValueError("Documento não pertence ao corpus permitido.")
        doc = json.loads((ROOT / f"data/processed/{document_id}.json").read_text(encoding="utf-8"))
        if not 1 <= page <= doc["total_pages"]:
            raise ValueError("Página fora do documento.")
        return DocumentResult(**{k: doc[k] for k in DocumentResult.model_fields if k not in {"page", "text"}}, page=page, text=doc["pages"][page-1])

    def topics(self) -> TopicsResult:
        groups = {}
        for doc in self.documents.values():
            topic = groups.setdefault(doc["topic_key"], {"documents": 0})
            topic["documents"] += 1
        labels = {"direito_penal": "Direito Penal", "processo_penal": "Processo Penal", "execucao_penal": "Execução Penal", "legislacao_penal": "Legislação penal especial"}
        topics = [Topic(topic_key=key, title=labels.get(key, key), documents=value["documents"],
                        chunks=len(self.collection.get(where={"topic_key": key}, include=[])["ids"])) for key, value in groups.items()]
        return TopicsResult(topics=topics, document_count=len(self.documents), chunk_count=self.collection.count())
