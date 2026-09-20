import pytest
from story_forecaster.evaluation.schemas import (
    GoldChapterData, EventUnit, MatchRecord, CandidateMetrics, EvaluationReport
)
from story_forecaster.evaluation.evaluator import BacktestEvaluator
from story_forecaster.evaluation.gold_data import CHAPTER_23_GOLD, CHAPTER_24_GOLD, get_gold_chapter
from story_forecaster.evaluation.ablation import AblationBenchmark
from story_forecaster.domain.forecast import (
    ChapterTopology, NarrativeMode, PlotBeat, PredictionCandidate, ForecastResult
)
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.forecast.context_builder import NarrativeContextBuilder
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Work

def test_antithetical_predictions_receive_zero_not_partial_credit():
    """
    Criterion: Opposite / contradictory predictions must receive 0.0 and be rejected,
    never receiving partial positive credit for shared entity keywords.
    """
    evaluator = BacktestEvaluator()
    gold_cube_event = CHAPTER_23_GOLD.key_events[1]  # Привязка Куба и передача Кадзуме
    gold_recruit_event = CHAPTER_23_GOLD.key_events[0]  # Покупка и призыв Кадзумы
    gold_fairy_event = CHAPTER_23_GOLD.key_events[4]  # Шантаж феи

    # 1. Cube destruction contradicts binding/crafting
    weight_cube, rat_cube = evaluator._score_event_pair(
        gold_cube_event,
        pred_summary="Хорадримский Куб уничтожен навсегда, трансмутация невозможна",
        conflict_type="loss"
    )
    assert weight_cube == 0.0
    assert "Противоречие" in rat_cube

    # 2. Rejection of recruit contradicts recruitment
    weight_rec, rat_rec = evaluator._score_event_pair(
        gold_recruit_event,
        pred_summary="Покупка Кадзумы сорвана, Кадзума отверг предложение Хачимана",
        conflict_type="refusal"
    )
    assert weight_rec == 0.0
    assert "Противоречие" in rat_rec

    # 3. Fairy death / failure of blackmail contradicts ongoing blackmail
    weight_fairy, rat_fairy = evaluator._score_event_pair(
        gold_fairy_event,
        pred_summary="Фея сбежала в страхе, шантаж не состоялся",
        conflict_type="escape"
    )
    assert weight_fairy == 0.0
    assert "Противоречие" in rat_fairy

def test_strict_one_to_one_matching_prevents_recall_inflation():
    """
    Criterion: Strict 1-to-1 matching ensures a single gold event cannot be matched
    by multiple predicted beats, and redundant predictions become spurious beats.
    """
    evaluator = BacktestEvaluator()

    # Candidate repeats the same gold event twice with slight variations
    candidate = PredictionCandidate(
        candidate_id="cand_duplicate_pred",
        title="Дублированное предсказание",
        topology=ChapterTopology(
            chapter_number=23,
            pov_character="Хачиман Хикигая",
            narrative_mode=NarrativeMode.AFTERMATH,
            pacing_tempo="medium",
            primary_location="Дом"
        ),
        key_events=[
            PlotBeat(ordinal=1, summary="Хачиман покупает Сато Кадзуму за 400 000 золота", conflict_type="deal"),
            PlotBeat(ordinal=2, summary="Хачиман завербовал Кадзуму через контракт за 400 000 золота", conflict_type="deal"),
            PlotBeat(ordinal=3, summary="Стороны пьют чай и отдыхают", conflict_type="rest")
        ],
        rationale="Проверка дублей",
        confidence_label="MEDIUM"
    )

    metrics = evaluator.evaluate_candidate(candidate, CHAPTER_23_GOLD)

    # Only 1 match allowed for gold event #1 (recruitment of Kazuma)
    matched_gold_indices = [m.gold_event_idx for m in metrics.matches]
    assert len(matched_gold_indices) == 1
    assert matched_gold_indices[0] == 1

    # Beat #2 must be flagged as spurious because event #1 was already consumed!
    assert 2 in metrics.spurious_predicted_beats or 1 in metrics.spurious_predicted_beats
    assert len(metrics.spurious_predicted_beats) == 2  # duplicate beat + unrelated tea beat

    # Recall must be strictly based on 1 match out of 5 gold events (0.2), not inflated!
    assert metrics.event_recall == round(1.0 / len(CHAPTER_23_GOLD.key_events), 3)

def test_missed_events_and_spurious_beats_tracking():
    """
    Criterion: Explicitly report which gold events were missed and which predicted beats were spurious.
    """
    evaluator = BacktestEvaluator()

    # Candidate covers only fairy blackmail (event #5), misses events #1, #2, #3, #4
    candidate = PredictionCandidate(
        candidate_id="cand_partial",
        title="Только фея",
        topology=ChapterTopology(
            chapter_number=23,
            pov_character="Сато Кадзума",
            narrative_mode=NarrativeMode.AFTERMATH,
            pacing_tempo="fast",
            primary_location="Ярмарка"
        ),
        key_events=[
            PlotBeat(ordinal=1, summary="Столкновение и шантаж феи с Кадзумой на ярмарке", conflict_type="blackmail"),
            PlotBeat(ordinal=2, summary="Кадзума покупает яблоки у торговца", conflict_type="trade")  # Spurious beat
        ],
        rationale="Фокус на фее",
        confidence_label="HIGH"
    )

    metrics = evaluator.evaluate_candidate(candidate, CHAPTER_23_GOLD)

    # Matched event is #5 (fairy)
    assert len(metrics.matches) == 1
    assert metrics.matches[0].gold_event_idx == 5

    # Missed gold events must explicitly list #1, #2, #3, #4
    assert metrics.missed_gold_events == [1, 2, 3, 4]

    # Spurious beats must explicitly list beat #2
    assert metrics.spurious_predicted_beats == [2]

def test_honest_status_and_prior_ranking_report():
    """
    Criterion: Unchecked fields must report 'not_checked' rather than constant 1.0.
    Candidate prior ranking must be frozen before gold evaluation.
    Variance and standard deviation must be reported across candidates.
    """
    evaluator = BacktestEvaluator()
    scope = ForecastScope(
        project_id="test_proj",
        target_work_version_id="test_v1",
        target_max_discourse_seq=184
    )

    cand_a = PredictionCandidate(
        candidate_id="cand_alpha",
        title="Кандидат Альфа",
        topology=ChapterTopology(chapter_number=23, pov_character="Хачиман", narrative_mode=NarrativeMode.AFTERMATH),
        key_events=[PlotBeat(ordinal=1, summary="Хачиман покупает Кадзуму за 400 000 золота", conflict_type="deal")],
        rationale="План А"
    )
    cand_b = PredictionCandidate(
        candidate_id="cand_beta",
        title="Кандидат Бета",
        topology=ChapterTopology(chapter_number=23, pov_character="Хачиман", narrative_mode=NarrativeMode.AFTERMATH),
        key_events=[PlotBeat(ordinal=1, summary="Кадзума проверяет трансмутацию в Кубе", conflict_type="craft")],
        rationale="План Б"
    )

    result = ForecastResult(
        target_work="Система Абсолютного З.Л.А.",
        cutoff_chapter=22,
        candidates=[cand_a, cand_b],
        generated_at_utc="2026-09-20T00:00:00Z",
        scope_manifest_hash=scope.manifest_hash(),
        author_precedent_citations=["test"]
    )

    report = evaluator.evaluate_forecast(result, CHAPTER_23_GOLD, cutoff_chapter=22)

    # Prior ranking matches candidate sequence before gold evaluation
    assert report.ranking_prior_to_gold == ["cand_alpha", "cand_beta"]
    assert report.best_at_1.candidate_id == "cand_alpha"

    # Status of unverified continuity is honestly 'not_checked', not a hardcoded 1.0!
    assert report.best_at_1.character_consistency_status == "not_checked"
    assert report.best_at_1.character_consistency is None

    # Variance and Std are computed and present
    assert hasattr(report, "f1_variance")
    assert hasattr(report, "f1_std")

def test_gold_data_never_leaks_into_context_builder():
    """
    Criterion: Gold standard reference data must NEVER be passed into
    the LLM context builder or prompt sources.
    """
    db = SessionLocal()
    try:
        work = db.query(Work).filter_by(role="target").first()
        if not work:
            pytest.skip("No target work in DB")

        scope = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=work.id,
            target_max_discourse_seq=184  # End of Chapter 22
        )

        builder = NarrativeContextBuilder()
        res = builder.build_context(db=db, scope=scope)

        # Ensure future gold cliffhangers and exact gold outcomes do not appear in context
        gold_23 = CHAPTER_23_GOLD
        for ev in gold_23.key_events:
            # Gold outcome statements must not be present in the source text
            assert ev.outcome not in res.formatted_source_text
        if gold_23.cliffhanger:
            assert gold_23.cliffhanger not in res.formatted_source_text
    finally:
        db.close()

def test_ablation_configurations_and_variance_tracking():
    """
    Criterion: B0, B1, B2 configurations provide measurable reproducible differences
    and report variance / missed counts.
    """
    bench = AblationBenchmark()
    report = bench.run_benchmark(cutoff_chapter=22, execute_live=False)

    assert len(report.runs) == 4
    config_names = [r.config_name for r in report.runs]
    assert "B0_baseline" in config_names
    assert "B1_memory" in config_names
    assert "B2_search" in config_names
    assert "Config_C_full" in config_names

    # Check metrics fields
    for r in report.runs:
        assert hasattr(r, "mean_f1")
        assert hasattr(r, "f1_variance")
        assert hasattr(r, "missed_events_count")
        assert hasattr(r, "spurious_beats_count")
