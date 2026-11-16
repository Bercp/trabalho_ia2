import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from penal.ingest import clean_text, token_chunks


def test_token_windows_cover_text_and_preserve_overlap():
    tokenizer = Tokenizer(WordLevel(vocab={"[UNK]": 0}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    text = " ".join(f"palavra{i}" for i in range(23))
    chunks = list(token_chunks(text, tokenizer, 10, 3))
    assert chunks[0].split()[-3:] == chunks[1].split()[:3]
    assert chunks[0].startswith("palavra0")
    assert chunks[-1].endswith("palavra22")
    assert all(len(tokenizer.encode(chunk).ids) <= 10 for chunk in chunks)


def test_invalid_overlap_does_not_loop():
    with pytest.raises(ValueError):
        list(token_chunks("texto", None, 10, 10))


def test_normalizes_line_breaks_without_losing_article():
    assert clean_text("Art. 25. Legí-\ntima   defesa\x00") == "Art. 25. Legítima defesa"
