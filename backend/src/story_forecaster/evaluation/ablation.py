from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.evaluation.gold_data import GoldChapterData, CHAPTER_23_GOLD
from story_forecaster.forecast.engine import ForecastEngine
from story_forecaster.evaluation.evaluator import BacktestEvaluator, EvaluationReport

class AblationRunResult(BaseModel):
    """Metrics summary for an ablation configuration run."""
    config_name: str
    description: str
    best_f1: float
    mean_f1: float = 0.0
    f1_variance: float = 0.0
    event_recall: float
    event_precision: float
    topology_score: Optional[float] = None
    missed_events_count: int = 0
    spurious_beats_count: int = 0

class AblationBenchmarkReport(BaseModel):
    """Aggregate benchmark report across B0, B1, B2, and Full configurations."""
    test_chapter: int
    runs: List[AblationRunResult]
    summary_analysis: str
    is_synthetic_demonstration: bool = Field(
        True,
        description="True for static illustrative baseline; False when live experimental runs are executed"
    )

class AblationBenchmark:
    """
    Evaluates individual component contributions (M4 specification):
    - B0: Baseline (recent sliding-window context only; no memory, no retrieval, no canon, no tropes)
    - B1: Context + Memory (EvidenceReducer + active threads + Theory of Mind epistemic states)
    - B2: Context + Memory + Search (BM25 dynamic retrieval from active goals)
    - Config_Full: Full architecture (+ Canon registry + Authorial precedents)
    """

    def __init__(self, engine: Optional[ForecastEngine] = None, evaluator: Optional[BacktestEvaluator] = None):
        self.engine = engine or ForecastEngine()
        self.evaluator = evaluator or BacktestEvaluator()

    def run_benchmark(
        self,
        gold_chapter: GoldChapterData = CHAPTER_23_GOLD,
        cutoff_chapter: int = 22,
        execute_live: bool = False
    ) -> AblationBenchmarkReport:
        from story_forecaster.db import SessionLocal
        from story_forecaster.db.models import Work, WorkVersion, Chapter, Scene

        db = SessionLocal()
        try:
            work = db.query(Work).filter_by(role="target").first()
            project_id = work.project_id if work else "default"
            latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first() if work else None
            version_id = latest_ver.id if latest_ver else "target_v1"

            target_ch = db.query(Chapter).filter(
                (Chapter.work_version_id == version_id) if latest_ver else True,
                Chapter.ordinal == cutoff_chapter
            ).first() if latest_ver else None

            last_sc = db.query(Scene).filter_by(chapter_id=target_ch.id).order_by(Scene.discourse_seq.desc()).first() if target_ch else None
            max_seq = last_sc.discourse_seq if last_sc else 184
        finally:
            db.close()

        scope = ForecastScope(
            project_id=project_id,
            target_work_version_id=version_id,
            target_max_discourse_seq=max_seq,
            mode="retrospective"
        )

        configs_meta = [
            ("B0_baseline", "Только недавний контекст (без retrieval, без канона, без тропов, без расширенной памяти)", {
                "disable_retrieval": True, "disable_canon": True, "disable_author": True, "disable_memory": True
            }),
            ("B1_memory", "Недавний контекст + память (EvidenceReducer + активные линии + эпистемика)", {
                "disable_retrieval": True, "disable_canon": True, "disable_author": True, "disable_memory": False
            }),
            ("B2_search", "Недавний контекст + память + динамический поиск BM25 от активных целей", {
                "disable_retrieval": False, "disable_canon": True, "disable_author": True, "disable_memory": False
            }),
            ("Config_C_full", "Полная архитектура (Память + Поиск + Канон + Авторские тропы)", {
                "disable_retrieval": False, "disable_canon": False, "disable_author": False, "disable_memory": False
            })
        ]

        if not execute_live:
            static_scores = [
                (0.615, 0.500, 0.800, 0.70, 0.550, 0.005, 2, 1),
                (0.750, 0.650, 0.880, 0.85, 0.700, 0.004, 1, 1),
                (0.833, 0.750, 0.940, 0.90, 0.780, 0.003, 1, 0),
                (0.889, 0.800, 1.000, 1.00, 0.850, 0.002, 0, 0)
            ]
            runs = []
            for (name, desc, _), (f1, rec, prec, topo, mean_f1, var, missed, spur) in zip(configs_meta, static_scores):
                runs.append(AblationRunResult(
                    config_name=name,
                    description=desc,
                    best_f1=f1,
                    mean_f1=mean_f1,
                    f1_variance=var,
                    event_recall=rec,
                    event_precision=prec,
                    topology_score=topo,
                    missed_events_count=missed,
                    spurious_beats_count=spur
                ))
            analysis = (
                f"[ДЕМОНСТРАЦИОННЫЙ СЦЕНАРИЙ: статические демонстрационные показатели; реальный запуск выполняется с execute_live=True]\n"
                f"Абляционный анализ для Главы {gold_chapter.chapter_ordinal}:\n"
                f"1. B0 baseline: F1={static_scores[0][0]}, Recall={static_scores[0][1]}, Precision={static_scores[0][2]}, Missed={static_scores[0][6]}.\n"
                f"2. B1 memory: F1={static_scores[1][0]}, Recall={static_scores[1][1]}, Precision={static_scores[1][2]}, Missed={static_scores[1][6]}.\n"
                f"3. B2 search: F1={static_scores[2][0]}, Recall={static_scores[2][1]}, Precision={static_scores[2][2]}, Missed={static_scores[2][6]}.\n"
                f"4. Config C full: F1={static_scores[3][0]}, Recall={static_scores[3][1]}, Precision={static_scores[3][2]}, Missed={static_scores[3][6]}."
            )
            return AblationBenchmarkReport(
                test_chapter=gold_chapter.chapter_ordinal,
                runs=runs,
                summary_analysis=analysis,
                is_synthetic_demonstration=True
            )

        # Live ablation execution: run actual forecast under each configuration
        runs = []
        for name, desc, kwargs in configs_meta:
            result = self.engine.run_forecast(
                scope=scope,
                num_candidates=3,
                persist_run=False,
                **kwargs
            )
            report = self.evaluator.evaluate_forecast(result, gold_chapter, cutoff_chapter=cutoff_chapter)
            runs.append(AblationRunResult(
                config_name=name,
                description=desc,
                best_f1=report.oracle_at_k.event_f1,
                mean_f1=report.mean_f1,
                f1_variance=report.f1_variance,
                event_recall=report.oracle_at_k.event_recall,
                event_precision=report.oracle_at_k.event_precision,
                topology_score=report.oracle_at_k.topology_score,
                missed_events_count=len(report.oracle_at_k.missed_gold_events),
                spurious_beats_count=len(report.oracle_at_k.spurious_predicted_beats)
            ))

        analysis = (
            f"[ЭКСПЕРИМЕНТАЛЬНЫЙ ЗАПУСК: эмпирически измеренные показатели для Главы {gold_chapter.chapter_ordinal}]\n"
            f"1. B0 baseline: F1={runs[0].best_f1}, Recall={runs[0].event_recall}, Missed={runs[0].missed_events_count}\n"
            f"2. B1 memory: F1={runs[1].best_f1}, Recall={runs[1].event_recall}, Missed={runs[1].missed_events_count}\n"
            f"3. B2 search: F1={runs[2].best_f1}, Recall={runs[2].event_recall}, Missed={runs[2].missed_events_count}\n"
            f"4. Config C full: F1={runs[3].best_f1}, Recall={runs[3].event_recall}, Missed={runs[3].missed_events_count}"
        )

        return AblationBenchmarkReport(
            test_chapter=gold_chapter.chapter_ordinal,
            runs=runs,
            summary_analysis=analysis,
            is_synthetic_demonstration=False
        )
