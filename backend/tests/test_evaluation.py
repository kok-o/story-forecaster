import pytest
from story_forecaster.evaluation.schemas import GoldChapterData, EventUnit
from story_forecaster.evaluation.evaluator import BacktestEvaluator
from story_forecaster.evaluation.gold_data import CHAPTER_23_GOLD
from story_forecaster.domain.forecast import (
    ChapterTopology, NarrativeMode, PlotBeat, PredictionCandidate, ForecastResult
)
from story_forecaster.domain.scope import ForecastScope

def test_backtest_evaluator_matching():
    evaluator = BacktestEvaluator()

    # Create candidate matching gold events
    candidate = PredictionCandidate(
        candidate_id="cand_test_1",
        title="Испытание Куба и выход на ярмарку",
        topology=ChapterTopology(
            chapter_number=23,
            pov_character="Хачиман Хикигая / Сато Кадзума",
            narrative_mode=NarrativeMode.AFTERMATH,
            pacing_tempo="medium",
            primary_location="Квартира в Фудзими / Ярмарка Осколка"
        ),
        key_events=[
            PlotBeat(
                ordinal=1,
                summary="Хачиман покупает и призывает Сато Кадзуму за 400 000 золота ради удачи в крафте",
                conflict_type="negotiation"
            ),
            PlotBeat(
                ordinal=2,
                summary="Привязка Хорадримского Куба к Кадзуме и проверка трансмутации",
                conflict_type="crafting"
            ),
            PlotBeat(
                ordinal=3,
                summary="Сато Кадзума отправляется на ярмарку системного осколка искать редкие ингредиенты",
                conflict_type="exploration"
            ),
            PlotBeat(
                ordinal=4,
                summary="Столкновение и шантаж феи с Кадзумой на ярмарке из-за пыльцы",
                conflict_type="blackmail"
            )
        ],
        rationale="Кадзума идеально подходит под удачу крафта в Системе",
        confidence_label="HIGH"
    )

    metrics = evaluator.evaluate_candidate(candidate, CHAPTER_23_GOLD)
    assert metrics.topology_score == 1.0
    assert metrics.event_recall > 0.6
    assert metrics.event_precision > 0.7
    assert metrics.event_f1 > 0.6
    assert len(metrics.matches) <= len(candidate.key_events)

    # Verify 1-to-1 matching: all matched gold indices must be unique
    matched_gold = [m.gold_event_idx for m in metrics.matches]
    assert len(matched_gold) == len(set(matched_gold))

def test_backtest_evaluator_oracle_ranking():
    evaluator = BacktestEvaluator()

    scope = ForecastScope(
        project_id="test_proj",
        target_work_version_id="test_v1",
        target_max_discourse_seq=184
    )

    # Candidate 1: low match
    cand_low = PredictionCandidate(
        candidate_id="cand_1",
        title="Атака на школу",
        topology=ChapterTopology(
            chapter_number=23,
            pov_character="Такаги Сая",
            narrative_mode=NarrativeMode.ACTION,
            pacing_tempo="fast",
            primary_location="Школа Фудзими"
        ),
        key_events=[
            PlotBeat(ordinal=1, summary="Ученики спорят о правилах клуба", conflict_type="social"),
            PlotBeat(ordinal=2, summary="Коити Сидо собирает своих сторонников", conflict_type="intrigue")
        ],
        rationale="Внезапный школьный конфликт",
        confidence_label="LOW"
    )

    # Candidate 2: high match
    cand_high = PredictionCandidate(
        candidate_id="cand_2",
        title="Сато Кадзума и ярмарка осколка",
        topology=ChapterTopology(
            chapter_number=23,
            pov_character="Сато Кадзума",
            narrative_mode=NarrativeMode.AFTERMATH,
            pacing_tempo="medium",
            primary_location="Ярмарка"
        ),
        key_events=[
            PlotBeat(ordinal=1, summary="Призыв Сато Кадзумы и передача Хорадримского Куба", conflict_type="deal"),
            PlotBeat(ordinal=2, summary="Кадзума выходит на ярмарку системного осколка", conflict_type="trade"),
            PlotBeat(ordinal=3, summary="Конфликт и шантаж феи против Кадзумы", conflict_type="blackmail")
        ],
        rationale="Логическое продолжение контракта",
        confidence_label="HIGH"
    )

    forecast_res = ForecastResult(
        target_work="Система Абсолютного З.Л.А.",
        cutoff_chapter=22,
        candidates=[cand_low, cand_high],
        generated_at_utc="2026-09-20T00:00:00Z",
        scope_manifest_hash=scope.manifest_hash(),
        author_precedent_citations=["test citation"]
    )

    report = evaluator.evaluate_forecast(forecast_res, CHAPTER_23_GOLD, cutoff_chapter=22)
    assert report.total_candidates == 2
    assert report.best_at_1.candidate_id == "cand_1"
    assert report.oracle_at_k.candidate_id == "cand_2"
    assert report.oracle_at_k.event_f1 > report.best_at_1.event_f1

def test_backtest_evaluator_negation_rejection():
    """Verify that contradictory negations receive 0.0 rather than 1.0."""
    evaluator = BacktestEvaluator()
    gold_cube_event = CHAPTER_23_GOLD.key_events[1]  # Привязка Хорадримского Куба и трансмутация

    contradictory_summary = "Хорадримский Куб уничтожен навсегда, крафт невозможен."
    weight, rationale = evaluator._score_event_pair(gold_cube_event, contradictory_summary, conflict_type="loss")

    assert weight == 0.0
    assert "Противоречие" in rationale

def test_backtest_evaluator_chapter_24_gold():
    """Verify that Chapter 24 gold standard is registered and evaluable."""
    from story_forecaster.evaluation.gold_data import get_gold_chapter
    gold_24 = get_gold_chapter(24)
    assert gold_24.chapter_ordinal == 24
    assert len(gold_24.key_events) >= 3

