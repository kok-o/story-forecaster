import math
import re
from typing import List, Dict, Tuple, Any

def tokenize_for_search(text: str) -> List[str]:
    """
    Search-specific normalizer:
    - Lowercase
    - Replace 'ё' -> 'е'
    - Extract alphanum tokens of length >= 2
    """
    clean_text = text.lower().replace("ё", "е")
    return re.findall(r"\b[а-яa-z0-9_]{2,}\b", clean_text)

class BM25Index:
    """
    BM25 lexical index implementing the project-specified formula:
    IDF = log(1 + (N - df + 0.5) / (df + 0.5))
    k1 = 1.2, b = 0.75
    """

    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: List[str] = []
        self.doc_lengths: Dict[str, int] = {}
        self.doc_term_freqs: Dict[str, Dict[str, int]] = {}
        self.doc_freqs: Dict[str, int] = {}
        self.total_docs: int = 0
        self.avg_doc_len: float = 0.0

    def add_document(self, doc_id: str, text: str) -> None:
        """Adds a document to the index."""
        tokens = tokenize_for_search(text)
        doc_len = len(tokens)
        self.doc_ids.append(doc_id)
        self.doc_lengths[doc_id] = doc_len

        tf: Dict[str, int] = {}
        seen_terms = set()
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
            seen_terms.add(token)

        self.doc_term_freqs[doc_id] = tf
        for term in seen_terms:
            self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

    def build(self) -> None:
        """Computes aggregate index statistics (total docs, avgdoclen)."""
        self.total_docs = len(self.doc_ids)
        if self.total_docs > 0:
            total_len = sum(self.doc_lengths.values())
            self.avg_doc_len = total_len / self.total_docs
        else:
            self.avg_doc_len = 0.0

    def compute_idf(self, term: str) -> float:
        """Computes Robertson-Spärck Jones IDF with smoothing."""
        df = self.doc_freqs.get(term, 0)
        numerator = self.total_docs - df + 0.5
        denominator = df + 0.5
        return math.log(1.0 + (numerator / denominator))

    def score_document(self, query_terms: List[str], doc_id: str) -> float:
        """Calculates BM25 relevance score for a given document."""
        doc_len = self.doc_lengths.get(doc_id, 0)
        if doc_len == 0 or self.avg_doc_len == 0.0:
            return 0.0

        score = 0.0
        tf_dict = self.doc_term_freqs.get(doc_id, {})
        len_norm = 1.0 - self.b + self.b * (doc_len / self.avg_doc_len)

        for term in query_terms:
            tf = tf_dict.get(term, 0)
            if tf > 0:
                idf = self.compute_idf(term)
                term_score = idf * (tf * (self.k1 + 1.0)) / (tf + self.k1 * len_norm)
                score += term_score

        return score

    def search(self, query: str, top_k: int = 30) -> List[Tuple[str, float]]:
        """Executes ranked BM25 search over all indexed documents."""
        query_terms = tokenize_for_search(query)
        if not query_terms or self.total_docs == 0:
            return []

        scores: List[Tuple[str, float]] = []
        for doc_id in self.doc_ids:
            s = self.score_document(query_terms, doc_id)
            if s > 0.0:
                scores.append((doc_id, round(s, 4)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
