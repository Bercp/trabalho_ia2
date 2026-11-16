from penal.store import LexicalIndex, query_terms


def test_query_focus_keeps_legal_subject_and_article_numbers():
    assert query_terms("O que é legítima defesa no Código Penal?") == ["legitima", "defesa"]
    assert "25" in query_terms("O que diz o artigo 25 do Código Penal?")


def test_lexical_search_obeys_category_and_prioritizes_subject():
    rows = {
        "a": {"text": "Legítima defesa no artigo 25", "meta": {"topic_key": "direito_penal"}},
        "b": {"text": "Defesa técnica no processo penal", "meta": {"topic_key": "processo_penal"}},
        "c": {"text": "Aplicação das penas", "meta": {"topic_key": "direito_penal"}},
    }
    index = LexicalIndex(rows)
    assert index.search(query_terms("legítima defesa"), None)[0] == "a"
    assert index.search(query_terms("legítima defesa"), "processo_penal") == ["b"]
