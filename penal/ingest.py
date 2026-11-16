"""Extração por página e janelas de tokens do próprio embedder."""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader
from tokenizers import Tokenizer

from penal.config import ROOT, settings
from penal.embeddings import embed_passages, embedder
from penal.schemas import Chunk


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\x00", "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def token_chunks(text: str, tokenizer, size: int, overlap: int):
    if not 0 <= overlap < size:
        raise ValueError("Overlap deve ser menor que chunk_size.")
    encoded = tokenizer.encode(text, add_special_tokens=False)
    offsets = encoded.offsets
    for start in range(0, len(offsets), size - overlap):
        end = min(start + size, len(offsets))
        yield text[offsets[start][0]:offsets[end - 1][1]]
        if end == len(offsets):
            break


def ingest() -> dict:
    from penal.store import connect, index_signature

    config = settings()
    manifest = json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))
    if len(manifest) < 5:
        raise ValueError("O RF01 exige pelo menos cinco documentos jurídicos.")
    processed = ROOT / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    tokenizer = Tokenizer.from_str(embedder().model.tokenizer.to_str())
    # Limite explícito: sem truncamento na fase de chunking de documentos longos.
    tokenizer.no_truncation()
    chunks = []
    documents = []
    for item in manifest:
        path = ROOT / "data/raw" / item["filename"]
        reader = PdfReader(path)
        pages = [clean_text(page.extract_text() or "") for page in reader.pages]
        if not any(len(t) > 50 for t in pages):
            raise ValueError(f"PDF sem texto extraível; exige OCR: {path.name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        doc = {**item, "sha256": digest, "total_pages": len(pages), "pages": pages}
        (processed / f'{item["document_id"]}.json').write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        documents.append({k: v for k, v in doc.items() if k != "pages"})
        count = 0
        for page_no, text in enumerate(pages, 1):
            if len(text) < 60:
                continue
            for n, piece in enumerate(token_chunks(text, tokenizer, config.chunk_size, config.chunk_overlap)):
                if len(piece) < 35:
                    continue
                chunk_id = f'{item["document_id"]}-p{page_no}-c{n}-{digest[:8]}'
                chunks.append(Chunk(chunk_id=chunk_id, text=piece, page=page_no, **item))
                count += 1
        print(f'{item["title"]}: {len(pages)} páginas, {count} chunks', flush=True)
    client = connect()
    # Staging: o índice ativo só é trocado depois de todos os batches concluírem.
    collection_name = "penal_" + hashlib.sha256((index_signature() + "".join(d["sha256"] for d in documents)).encode()).hexdigest()[:20]
    collection = client.get_or_create_collection(collection_name, embedding_function=None, configuration={"hnsw": {"space": "cosine"}})
    for start in range(0, len(chunks), 64):
        batch = chunks[start:start + 64]
        vectors = embed_passages([c.text for c in batch])
        collection.upsert(ids=[c.chunk_id for c in batch], documents=[c.text for c in batch], embeddings=vectors,
                          metadatas=[c.model_dump(exclude={"chunk_id", "text", "similarity", "retrieval_method"}) for c in batch])
        print(f'Indexação: {min(start+64, len(chunks))}/{len(chunks)}', flush=True)
    index = {"collection": collection_name, "signature": index_signature(), "documents": documents,
             "chunk_count": len(chunks), "chunk_size": config.chunk_size, "chunk_overlap": config.chunk_overlap,
             "embedding_model": config.embedding_model}
    staged = processed / "index.tmp"
    staged.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    staged.replace(processed / "index.json")
    print(json.dumps({"documents": len(documents), "chunks": len(chunks), "collection": collection_name}))
    return index


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    ingest()
