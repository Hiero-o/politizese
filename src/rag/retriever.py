import re
import unicodedata
from collections import Counter
from math import log
from pathlib import Path

from langchain_core.documents import Document

from src.rag.vector_store import create_vector_store

STOPWORDS = {
    "",
    "",
}

def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())

    return "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )
    
    #falta definir DEAFULT_TOP_K, DEFAULT_CANDIDATE_K e outras coisas.


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_text(text)
    tokens = re.findall(r"[a-z0-9]+", normalized)

    return [
        token
        for token in tokens
        if token not in STOPWORDS
    ]
    
    
    
    