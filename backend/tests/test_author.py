import pytest
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.author.precedents import AuthorPrecedentLibrary

def test_author_precedent_query():
    lib = AuthorPrecedentLibrary()
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=192
    )

    # Query for fairy blackmail tags
    matches = lib.query_precedents(scope, ["fairy_blackmail", "trade"])
    assert len(matches) >= 1
    assert any("вымогать" in m.abstract_situation.lower() for m in matches)

    # Check author profile
    profile = lib.get_profile()
    assert profile.author_name == "N.B."
    assert len(profile.signature_traits) >= 5
    assert len(profile.transitions) >= 4
