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
    best_at_1_f1: float = 0.0
    oracle_at_k_f1: float = 0.0
    mean_f1: float = 0.0
    f1_variance: float = 0.0
    event_recall: float
    event_precision: float
    topology_score: Optional[float] = None
    missed_events_count: int = 0
    spurious_beats_count: int = 0
    run_id: Optional[str] = None
    disable_flags: Dict[str, bool] = Field(default_factory=dict)

class AblationBenchmarkReport(BaseModel):
    """Aggregate benchmark report across ablation configurations."""
    test_chapter: int
    runs: List[AblationRunResult]
    summary_analysis: str
    is_synthetic_demonstration: bool = Field(
        True,
        description="True for static illustrative baseline; False when live experimental runs are executed"
    )

class AblationBenchmark:
    """
    Evaluates individual component contributions (M4/M5 specification):
    - B0: Baseline (recent sliding-window context only; no memory, no retrieval, no canon, no tropes)
    - B1: Context + Memory (EvidenceReducer + active threads + Theory of Mind epistemic states)
    - B2: Context + Memory + Search (BM25 dynamic retrieval from active goals)
    - B3: Context + Memory + Canon (Canon alignments overlay)
    - B4: Context + Memory + Author (Author precedent transitions)
    - Config_C_full: Full architecture (Memory + Search + Canon + Author)
    """

    def __init__(self, engine: Optional[ForecastEngine] = None, evaluator: Optional[BacktestEvaluator] = None):
        self.engine = engine or ForecastEngine()
        self.evaluator = evaluator or BacktestEvaluator()

    def run_benchmark(
        self,
        gold_chapter: GoldChapterData = CHAPTER_23_GOLD,
        cutoff_chapter: int = 22,
        execute_live: bool = False,
        include_fine_grained: bool = False
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

        standard_configs = [
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

        fine_grained_configs = [
            ("B0_baseline", "Только недавний контекст (без retrieval, без канона, без тропов, без памяти)", {
                "disable_retrieval": True, "disable_canon": True, "disable_author": True, "disable_memory": True
            }),
            ("B1_memory", "Недавний контекст + память (EvidenceReducer)", {
                "disable_retrieval": True, "disable_canon": True, "disable_author": True, "disable_memory": False
            }),
            ("B2_search", "Недавний контекст + память + поиск BM25", {
                "disable_retrieval": False, "disable_canon": True, "disable_author": True, "disable_memory": False
            }),
            ("B3_canon", "Недавний контекст + память + канонические оверлеи HOTD/KonoSuba", {
                "disable_retrieval": True, "disable_canon": False, "disable_author": True, "disable_memory": False
            }),
            ("B4_author", "Недавний контекст + память + авторские прецеденты N.B.", {
                "disable_retrieval": True, "disable_canon": True, "disable_author": False, "disable_memory": False
            }),
            ("Config_C_full", "Полная архитектура (Память + Поиск + Канон + Авторские прецеденты)", {
                "disable_retrieval": False, "disable_canon": False, "disable_author": False, "disable_memory": False
            }),
            ("Full_minus_canon", "Полная архитектура без канона (изоляция вклада канона)", {
                "disable_retrieval": False, "disable_canon": True, "disable_author": False, "disable_memory": False
            }),
            ("Full_minus_author", "Полная архитектура без авторских тропов (изоляция вклада автора)", {
                "disable_retrieval": False, "disable_canon": False, "disable_author": True, "disable_memory": False
            })
        ]

        configs_meta = fine_grained_configs if include_fine_grained else standard_configs

        if not execute_live:
            if include_fine_grained:
                static_scores = [
                    (0.615, 0.500, 0.800, 0.70, 0.550, 0.005, 2, 1),
                    (0.750, 0.650, 0.880, 0.85, 0.700, 0.004, 1, 1),
                    (0.833, 0.750, 0.940, 0.90, 0.780, 0.003, 1, 0),
                    (0.800, 0.700, 0.920, 0.90, 0.750, 0.004, 1, 1),
                    (0.810, 0.720, 0.930, 0.88, 0.760, 0.003, 1, 1),
                    (0.889, 0.800, 1.000, 1.00, 0.850, 0.002, 0, 0),
                    (0.840, 0.760, 0.950, 0.92, 0.800, 0.003, 1, 0),
                    (0.830, 0.750, 0.940, 0.90, 0.790, 0.003, 1, 0)
                ]
            else:
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
                f"Абляционный анализ компонентов для Главы {gold_chapter.chapter_ordinal}:\n"
                + "\n".join([f"- {r.config_name}: F1={r.best_f1}, Recall={r.event_recall}, Precision={r.event_precision}, Missed={r.missed_events_count}" for r in runs])
            )

            return AblationBenchmarkReport(
                test_chapter=gold_chapter.chapter_ordinal,
                runs=runs,
                summary_analysis=analysis,
                is_synthetic_demonstration=True
            )

        provider_cls = self.engine.provider.__class__.__name__.lower()
        provider_name = getattr(self.engine.provider, "name", getattr(self.engine.provider, "provider_name", provider_cls)).lower()
        is_provider_synthetic = "demo" in provider_name or "demo" in provider_cls or getattr(self.engine.provider, "is_mock", False)
        is_synthetic = (not execute_live) or is_provider_synthetic

        # Live ablation execution: run actual forecast under each configuration
        runs = []
        for name, desc, kwargs in configs_meta:
            result = self.engine.run_forecast(
                scope=scope,
                num_candidates=3,
                persist_run=True,
                **kwargs
            )
            report = self.evaluator.evaluate_forecast(result, gold_chapter, cutoff_chapter=cutoff_chapter)
            best_at_1 = report.mean_f1
            if hasattr(report, "best_candidate") and report.best_candidate:
                best_at_1 = report.best_candidate.event_f1

            runs.append(AblationRunResult(
                config_name=name,
                description=desc,
                best_f1=report.oracle_at_k.event_f1,
                best_at_1_f1=round(best_at_1, 4),
                oracle_at_k_f1=round(report.oracle_at_k.event_f1, 4),
                mean_f1=report.mean_f1,
                f1_variance=report.f1_variance,
                event_recall=report.oracle_at_k.event_recall,
                event_precision=report.oracle_at_k.event_precision,
                topology_score=report.oracle_at_k.topology_score,
                missed_events_count=len(report.oracle_at_k.missed_gold_events),
                spurious_beats_count=len(report.oracle_at_k.spurious_predicted_beats),
                run_id=getattr(result, "run_id", None),
                disable_flags=kwargs
            ))

        analysis = (
            f"[{'СИНТЕТИЧЕСКИЙ ДЕМО-ПРОГОН' if is_synthetic else 'ЭМПИРИЧЕСКИЙ ЗАПУСК'}: показатели для Главы {gold_chapter.chapter_ordinal}]\n"
            + "\n".join([f"- {r.config_name}: Best@1={r.best_at_1_f1}, Oracle@K={r.oracle_at_k_f1}, Recall={r.event_recall}, Missed={r.missed_events_count}" for r in runs])
        )

        return AblationBenchmarkReport(
            test_chapter=gold_chapter.chapter_ordinal,
            runs=runs,
            summary_analysis=analysis,
            is_synthetic_demonstration=is_synthetic
        )
