import math
import re
from typing import List, Dict, Tuple, Any

# Russian Porter Stemmer tables
_VOWELS = set("аеиоуыэюя")

_PERFECTIVE_GERUND_GROUP1 = ("в", "вши", "вшись")
_PERFECTIVE_GERUND_GROUP2 = ("ив", "ивши", "ившись", "ыв", "ывши", "ывшись")

_ADJECTIVE_ENDINGS = (
    "ее", "ие", "ое", "ые", "ими", "ыми", "ей", "ий", "ой", "ый",
    "ем", "им", "ом", "ым", "его", "ого", "ему", "ому", "их", "ых",
    "ую", "юю", "ая", "яя", "ою", "ею"
)

_PARTICIPLE_GROUP1 = ("ем", "нн", "вш", "ющ", "щ")
_PARTICIPLE_GROUP2 = ("ивш", "ывш", "ующ")

_REFLEXIVE_ENDINGS = ("ся", "сь")

_VERB_GROUP1 = (
    "ла", "на", "ете", "йте", "ли", "й", "л", "ем", "н", "ло", "но",
    "ет", "ют", "ны", "ть", "ешь", "нно"
)
_VERB_GROUP2 = (
    "ила", "ыла", "ена", "ите", "или", "ыли", "ий", "ил", "ыл", "им",
    "ым", "ен", "ило", "ыло", "ено", "ят", "ует", "уют", "ины", "ыны",
    "ить", "ыть", "ишь", "ей", "ейте", "уй", "уйте"
)

_NOUN_ENDINGS = (
    "ами", "ями", "иями", "ией", "иям", "ием",
    "ев", "ов", "ье", "еи", "ии", "ей", "ой", "ем", "ям", "ам",
    "ом", "ах", "их", "ях", "ию", "ью",
    "а", "е", "и", "о", "у", "ы", "ь", "ю", "я"
)

_SUPERLATIVE_ENDINGS = ("ейше", "ейш")
_DERIVATIONAL_ENDINGS = ("ость", "ост")


def stem_russian_word(word: str) -> str:
    """
    Applies deterministic Russian stemming (Porter-based) to normalize inflections
    (cases, tenses, adjectives, gerunds) to a shared morphological root.
    """
    if len(word) <= 2:
        return word

    # 1. Find RV (region after the first vowel)
    rv_idx = -1
    for i, ch in enumerate(word):
        if ch in _VOWELS:
            rv_idx = i + 1
            break

    if rv_idx == -1 or rv_idx >= len(word):
        return word

    rv = word[rv_idx:]

    # Helper: strip ending if present in RV
    def strip_ending(source_rv: str, endings: tuple, check_preceding: str = "") -> Tuple[str, bool]:
        for end in sorted(endings, key=len, reverse=True):
            if source_rv.endswith(end):
                pos = len(source_rv) - len(end)
                if check_preceding:
                    # Look at character right before the ending in whole word
                    whole_pos = rv_idx + pos
                    if whole_pos > 0 and word[whole_pos - 1] in check_preceding:
                        return source_rv[:pos], True
                else:
                    return source_rv[:pos], True
        return source_rv, False

    # Step 1: Perfective gerund OR (reflexive + (adjective / verb / noun))
    new_rv, matched = strip_ending(rv, _PERFECTIVE_GERUND_GROUP1, check_preceding="ая")
    if not matched:
        new_rv, matched = strip_ending(rv, _PERFECTIVE_GERUND_GROUP2)

    if not matched:
        # Strip reflexive
        rv_no_refl, _ = strip_ending(rv, _REFLEXIVE_ENDINGS)
        # Try adjective
        adj_rv, adj_matched = strip_ending(rv_no_refl, _ADJECTIVE_ENDINGS)
        if adj_matched:
            # Check following participle
            part_rv, _ = strip_ending(adj_rv, _PARTICIPLE_GROUP1, check_preceding="ая")
            if part_rv == adj_rv:
                part_rv, _ = strip_ending(adj_rv, _PARTICIPLE_GROUP2)
            new_rv = part_rv
        else:
            # Try verb
            verb_rv, verb_matched = strip_ending(rv_no_refl, _VERB_GROUP1, check_preceding="ая")
            if not verb_matched:
                verb_rv, verb_matched = strip_ending(rv_no_refl, _VERB_GROUP2)
            if verb_matched:
                new_rv = verb_rv
            else:
                # Try noun
                noun_rv, _ = strip_ending(rv_no_refl, _NOUN_ENDINGS)
                new_rv = noun_rv

    # Step 2: Strip 'и' if present at end of RV
    if new_rv.endswith("и"):
        new_rv = new_rv[:-1]

    # Step 3: Derivational
    deriv_rv, deriv_matched = strip_ending(new_rv, _DERIVATIONAL_ENDINGS)
    if deriv_matched:
        new_rv = deriv_rv

    # Step 4: Superlative, 'ь', double 'нн'
    sup_rv, _ = strip_ending(new_rv, _SUPERLATIVE_ENDINGS)
    if sup_rv.endswith("ь"):
        sup_rv = sup_rv[:-1]
    if sup_rv.endswith("нн"):
        sup_rv = sup_rv[:-1]

    return word[:rv_idx] + sup_rv


def tokenize_for_search(text: str, stem: bool = True) -> List[str]:
    """
    Search-specific normalizer:
    - Lowercase
    - Replace 'ё' -> 'е'
    - Extract alphanum tokens of length >= 2
    - Morphologically stem Russian words (e.g. 'кубом' -> 'куб', 'пыльцы' -> 'пыльц')
    """
    clean_text = text.lower().replace("ё", "е")
    raw_tokens = re.findall(r"\b[а-яa-z0-9_]{2,}\b", clean_text)
    if not stem:
        return raw_tokens

    stemmed: List[str] = []
    for token in raw_tokens:
        if re.match(r"^[а-я]+$", token):
            stemmed.append(stem_russian_word(token))
        else:
            stemmed.append(token)
    return stemmed


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
        tokens = tokenize_for_search(text, stem=True)
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
        query_terms = tokenize_for_search(query, stem=True)
        if not query_terms or self.total_docs == 0:
            return []

        scores: List[Tuple[str, float]] = []
        for doc_id in self.doc_ids:
            s = self.score_document(query_terms, doc_id)
            if s > 0.0:
                scores.append((doc_id, round(s, 4)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
