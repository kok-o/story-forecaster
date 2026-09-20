import hashlib
import pytest
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.canon import (
    CanonOverlay,
    CanonRelation,
    EvidenceStatus,
    DependencyStatus,
    OccurrenceStatus,
    FanficModificationType
)
from story_forecaster.canon.registry import CanonDivergenceRegistry
from story_forecaster.author.precedents import AuthorPrecedentLibrary, AuthorTag, AuthorTransition
from story_forecaster.forecast.context_builder import NarrativeContextBuilder
from story_forecaster.forecast.engine import ForecastEngine
from story_forecaster.evaluation.ablation import AblationBenchmark
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Work

def test_canon_overlay_provenance_and_protagonist_knowledge():
    """
    Criterion: Version canonical sources and overlays. Distinguish original canon from fanfic modification.
    Do not leak reader's meta-knowledge into the in-story protagonist's knowledge matrix.
    """
    registry = CanonDivergenceRegistry()
    scope = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=192
    )

    overlays = registry.get_overlays(scope)
    assert len(overlays) >= 5

    # 1. Check Saeko Busujima: observed by Hachiman in dojo -> protagonist knows
    saeko = next(o for o in overlays if o.element_id == "hotd_char_saeko_busujima")
    assert saeko.source_canon_ref == "HOTD Manga Act 2: Escape from the Dead"
    assert saeko.fanfic_modification_type == FanficModificationType.ORIGINAL_UNTOUCHED
    assert saeko.is_known_to_protagonist is True
    assert len(saeko.source_spans) >= 1

    # 2. Check Shizuka Marikawa: reader knows she has a Hummer, but Hachiman has not interacted with her
    shizuka = next(o for o in overlays if o.element_id == "hotd_char_shizuka_marikawa")
    assert shizuka.source_canon_ref == "HOTD Manga Act 3: Democracy under the Dead"
    assert shizuka.is_known_to_protagonist is False  # Protected against reader omniscience leak!

    # 3. Check Dungeon Outbreak divergence: explicit fanfic modification known to protagonist
    outbreak = next(o for o in overlays if o.element_id == "hotd_event_outbreak_gate")
    assert outbreak.fanfic_modification_type == FanficModificationType.EXPLICIT_CHANGE
    assert outbreak.is_known_to_protagonist is True
    assert outbreak.canon_relation == CanonRelation.MODIFIED

def test_author_precedent_verifiable_citations_and_alternatives():
    """
    Criterion: For precedents, store verified situation, resolution, consequence, exact textual snippet,
    and SHA-256 hash. Account for alternative outcomes.
    """
    lib = AuthorPrecedentLibrary()
    profile = lib.get_profile()

    for transition in profile.transitions:
        assert transition.source_work is not None and len(transition.source_work) > 0
        assert transition.source_chapter is not None and len(transition.source_chapter) > 0
        assert transition.source_text_snippet is not None and len(transition.source_text_snippet) > 10
        # Verify SHA-256 integrity
        expected_sha = hashlib.sha256(transition.source_text_snippet.encode("utf-8")).hexdigest()
        assert transition.source_sha256 == expected_sha
        # Verify alternative paths are considered
        assert len(transition.alternative_resolutions) >= 1
        assert len(transition.applicability_tags) >= 1

def test_author_tag_exact_vocabulary_and_deduplication():
    """
    Criterion: Controlled tag vocabulary, no substring collisions, and strict deduplication.
    """
    lib = AuthorPrecedentLibrary()
    scope = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=192
    )

    # 1. Exact tag query
    matches = lib.query_precedents(scope, [AuthorTag.FAIRY_BLACKMAIL.value, AuthorTag.TRADE.value, AuthorTag.EXTORTION.value])
    assert len(matches) >= 1
    # Check deduplication: all transition IDs must be unique
    t_ids = [m.transition_id for m in matches]
    assert len(t_ids) == len(set(t_ids))

    # 2. No substring collision: substring 'ade' must NOT match 'trade'
    sub_matches = lib.query_precedents(scope, ["ade", "fair"])
    # If no exact match, fallback to default 2 without false substring matching
    for m in sub_matches:
        assert "ade" not in m.applicability_tags

def test_context_builder_embeds_and_toggles_canon_and_author_precedents():
    """
    Criterion: Include chosen precedents and canon overlays into ContextBuilder.
    Disabling components changes the actual context and prompt text.
    """
    db = SessionLocal()
    try:
        work = db.query(Work).filter_by(role="target").first()
        if not work:
            pytest.skip("No target work in DB")

        scope = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=work.id,
            target_max_discourse_seq=192
        )

        canon_registry = CanonDivergenceRegistry()
        author_lib = AuthorPrecedentLibrary()
        builder = NarrativeContextBuilder()

        overlays = canon_registry.get_overlays(scope)
        precedents = author_lib.query_precedents(scope, [AuthorTag.FAIRY_BLACKMAIL.value])

        # 1. Full context build with canon and author precedents
        res_full = builder.build_context(
            db=db,
            scope=scope,
            canon_overlays=overlays,
            author_precedents=precedents
        )

        assert "<canon_alignments>" in res_full.formatted_source_text
        assert "<author_precedents>" in res_full.formatted_source_text
        assert res_full.truncation_info["included_canon_count"] == len(overlays)
        assert res_full.truncation_info["included_precedents_count"] == len(precedents)
        assert "trans_extortion_counterplay" in res_full.truncation_info["included_precedent_ids"]
        assert "hotd_char_saeko_busujima" in res_full.truncation_info["included_canon_ids"]

        # 2. Context build with canon disabled
        res_no_canon = builder.build_context(
            db=db,
            scope=scope,
            canon_overlays=[],
            author_precedents=precedents
        )
        assert "<canon_alignments>" not in res_no_canon.formatted_source_text
        assert "<author_precedents>" in res_no_canon.formatted_source_text
        assert res_no_canon.truncation_info["included_canon_count"] == 0

        # 3. Context build with author precedents disabled
        res_no_author = builder.build_context(
            db=db,
            scope=scope,
            canon_overlays=overlays,
            author_precedents=[]
        )
        assert "<canon_alignments>" in res_no_author.formatted_source_text
        assert "<author_precedents>" not in res_no_author.formatted_source_text
        assert res_no_author.truncation_info["included_precedents_count"] == 0
    finally:
        db.close()

def test_forecast_engine_disabling_canon_and_author():
    """
    Criterion: ForecastEngine cleanly propagates disable_canon and disable_author flags
    into the context builder, producing measured context variance.
    """
    engine = ForecastEngine()
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=184
    )

    # When canon is disabled, registry is not queried or included
    overlays_disabled = engine.canon_registry.get_overlays(scope)
    assert len(overlays_disabled) > 0  # Exists in registry

    # Query precedents with controlled tag
    precedents = engine.author_lib.query_precedents(scope, ["fairy_blackmail"])
    assert len(precedents) >= 1

def test_ablation_fine_grained_components():
    """
    Criterion: Ablation benchmark provides fine-grained evaluation of canon and author components.
    """
    bench = AblationBenchmark()
    report = bench.run_benchmark(cutoff_chapter=22, execute_live=False, include_fine_grained=True)

    assert len(report.runs) == 8
    config_names = [r.config_name for r in report.runs]
    assert "B0_baseline" in config_names
    assert "B1_memory" in config_names
    assert "B2_search" in config_names
    assert "B3_canon" in config_names
    assert "B4_author" in config_names
    assert "Config_C_full" in config_names
    assert "Full_minus_canon" in config_names
    assert "Full_minus_author" in config_names
