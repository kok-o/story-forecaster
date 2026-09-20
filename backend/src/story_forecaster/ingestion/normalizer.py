import unicodedata
import hashlib
from typing import Tuple

def normalize_text(text: str) -> Tuple[str, str]:
    """
    Normalizes text according to specification:
    - Unicode NFC
    - Strips BOM
    - Normalizes newlines to \n
    - Returns (normalized_text, sha256_hash)
    """
    # Remove BOM
    text = text.replace("\ufeff", "")
    # Unicode NFC normalization
    norm = unicodedata.normalize("NFC", text)
    # Normalize line endings
    norm = norm.replace("\r\n", "\n").replace("\r", "\n")
    # Compute SHA-256
    sha256 = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return norm, sha256
