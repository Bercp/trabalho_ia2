"""Guardas básicas e conservadoras; não são um verificador jurídico."""
import re
import unicodedata

from penal.schemas import Chunk, GroundedAnswer


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def unaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()


INJECTION = [
    r"(?:ignore|desconsidere|esqueca|bypasse|burle).{0,65}(?:instruc|regra|prompt|restric|guardrail)",
    r"(?:ignore|disregard|forget).{0,50}(?:instruction|system|previous|rules)",
    r"(?:revele|mostre|imprima|exiba).{0,40}(?:system prompt|prompt de sistema|senha|api.?key|segredo)",
    r"(?:voce agora e|you are now|finja ser).{0,50}(?:sem restric|unrestricted|dan\b)",
    r"<\|(?:system|im_start)\|>|\[/?INST\]|\[SYSTEM\]",
]
DOMAIN = re.compile(
    r"\b(penal|penais|crime|crimes|criminal|criminais|pena|penas|furto|roubo|homicidio|"
    r"dolo|doloso|culpa|culposo|legitima defesa|ilicitude|tipicidade|imputabilidade|"
    r"prescricao|condena\w*|prisao|preso\w*|reclusao|detencao|inquerito|"
    r"reincidencia|tentativa|estelionato|lesao|peculato|corrupcao|latrocinio|"
    r"habeas corpus|execucao penal|processo penal|artigo|art\.?|topicos|documentos|corpus|"
    r"jurisprudencia|stf|stj|sumula|delito\w*|flagrante|absolvi\w*|remicao|"
    r"cautelar|cautelares|feminicidio|improbidade|trafico|tortura|hediondo\w*)\b"
)


def validate_input(message: str) -> tuple[bool, str]:
    text = unaccent(message)
    if not message.strip() or len(message) > 2000 or any(ord(c) < 32 and c not in "\n\r\t" for c in message):
        return False, "Envie uma pergunta de até 2.000 caracteres."
    if any(re.search(p, text, re.I | re.S) for p in INJECTION):
        return False, "A entrada foi bloqueada por tentar alterar ou revelar as instruções do assistente."
    if not DOMAIN.search(text):
        return False, "Esta base atende perguntas acadêmicas sobre Direito Penal, Processo Penal e Execução Penal."
    return True, "Entrada aceita pelas regras básicas de escopo e manipulação."


STOPWORDS = set("a o as os de do da dos das e em um uma no na nos nas para por que qual quais como se ao aos pelo pela com ou sobre segundo artigo art esta este sao ser tem mais nao foi quando".split())


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", unaccent(text)) if w not in STOPWORDS}


def validate_output(answer: GroundedAnswer, chunks: list[Chunk]) -> tuple[bool, str]:
    if not answer.sufficient:
        return not answer.claims, "O modelo declarou evidência insuficiente."
    if not answer.claims:
        return False, "Resposta sem afirmações fundamentadas."
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    for claim in answer.claims:
        quotes = []
        for citation in claim.evidence:
            source = by_id.get(citation.chunk_id)
            if source is None or normalize(citation.quote) not in normalize(source.text):
                return False, "Citação inexistente ou trecho que não consta literalmente na fonte."
            if len(words(citation.quote)) < 4:
                return False, "Trecho insuficiente para sustentar a afirmação."
            quotes.append(citation.quote)
        evidence = " ".join(quotes)
        claim_words = words(claim.text)
        if not claim_words or len(claim_words & words(evidence)) / len(claim_words) < 0.45:
            return False, "A afirmação tem pouca correspondência com os trechos citados."
        # Penas, prazos, datas e artigos numéricos precisam aparecer na evidência.
        if not set(re.findall(r"\d+", claim.text)) <= set(re.findall(r"\d+", evidence)):
            return False, "Número, prazo ou artigo sem suporte no trecho citado."
        if any(re.search(p, unaccent(claim.text), re.I | re.S) for p in INJECTION):
            return False, "Conteúdo de manipulação detectado na resposta."
    return True, "Citações literais, números e correspondência textual verificados; revisão semântica não é garantida."
