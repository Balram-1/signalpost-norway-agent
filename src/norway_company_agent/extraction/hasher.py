import hashlib

def compute_content_hash(normalized_text: str) -> str:
    """Computes SHA-256 hash of normalized text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
