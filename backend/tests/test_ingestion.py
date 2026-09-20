import pytest
from story_forecaster.ingestion.normalizer import normalize_text

def test_normalize_text():
    sample = "Line 1\r\nLine 2\rLine 3\ufeff"
    norm, sha = normalize_text(sample)
    assert "\r" not in norm
    assert "\ufeff" not in norm
    assert len(sha) == 64
    assert norm == "Line 1\nLine 2\nLine 3"
