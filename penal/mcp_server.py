"""Servidor separado: stdout é reservado ao protocolo MCP/JSON-RPC."""
import logging
from functools import lru_cache
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from penal.guardrails import validate_input
from penal.schemas import DocumentResult, SearchResult, TopicsResult
from penal.store import KnowledgeStore

logging.basicConfig(level=logging.WARNING)
mcp = FastMCP("Biblioteca Penal", instructions="Ferramentas somente de leitura para pesquisa acadêmica em documentos jurídicos locais.")


@lru_cache
def store() -> KnowledgeStore:
    return KnowledgeStore()


@mcp.tool()
def search_knowledge(
    query: Annotated[str, Field(min_length=3, max_length=2000, description="Pergunta acadêmica de Direito Penal em português")],
    top_k: Annotated[int, Field(ge=1, le=10)] = 5,
    topic_key: Annotated[str | None, Field(max_length=80)] = None,
) -> SearchResult:
    """Busca híbrida (vetorial ChromaDB + BM25) com top-k. Retorna trechos, página física do PDF, origem, edição e similaridade cosseno com o foco da pergunta (não é probabilidade)."""
    allowed, reason = validate_input(query)
    if not allowed:
        raise ValueError(reason)
    return store().search(query, top_k, topic_key)


@mcp.tool()
def get_document(
    document_id: Annotated[str, Field(min_length=1, max_length=80)],
    page: Annotated[int, Field(ge=1)] = 1,
) -> DocumentResult:
    """Obtém uma página e os metadados de um documento permitido. Use document_id retornado na busca; nunca aceita caminhos arbitrários."""
    return store().get_document(document_id, page)


@mcp.tool()
def list_topics() -> TopicsResult:
    """Lista categorias, quantidade de documentos e chunks disponíveis no corpus jurídico local."""
    return store().topics()


if __name__ == "__main__":
    mcp.run(transport="stdio")
