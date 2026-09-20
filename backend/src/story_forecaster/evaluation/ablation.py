from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.evaluation.gold_data import GoldChapterData, CHAPTER_23_GOLD
from story_forecaster.forecast.engine import ForecastEngine
from story_forecaster.evaluation.evaluator import BacktestEvaluator, EvaluationReport

class AblationRunResult(BaseModel):
    config_name: str
    description: str
    best_f1: float
    event_recall: float
    event_precision: float
    topology_score: float

class AblationBenchmarkReport(BaseModel):
    test_chapter: int
    runs: List[AblationRunResult]
    summary_analysis: str
    is_synthetic_demonstration: bool = Field(
        True,
        description="Маркер синтетических/иллюстративных данных: динамические эксперименты не проводились"
    )

class AblationBenchmark:
    """
    Evaluates individual component contributions (M10/M12 specification):
    - B0: Baseline (no canon registry, no author tropes library)
    - Config A: Retrieval-only (BM25 search active, no canon, no tropes)
    - Config B: Canon-guided (Canon registry active, no author tropes)
    - Config C: Full Architecture (Narrative Memory + Canon Registry + Author Tropes + BM25 RRF)
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
            ("Config_A_retrieval", "Гибридный поиск (BM25+RRF), но без канона и без авторских тропов", {
                "disable_retrieval": False, "disable_canon": True, "disable_author": True, "disable_memory": True
            }),
            ("Config_B_canon", "5-статусный реестр канона + память сюжета, без авторских тропов", {
                "disable_retrieval": True, "disable_canon": False, "disable_author": True, "disable_memory": False
            }),
            ("Config_C_full", "Полная архитектура (Память + Канон + Авторские тропы + BM25/RRF)", {
                "disable_retrieval": False, "disable_canon": False, "disable_author": False, "disable_memory": False
            })
        ]

        if not execute_live:
            static_scores = [
                (0.615, 0.500, 0.800, 0.70),
                (0.727, 0.600, 0.900, 0.80),
                (0.800, 0.700, 0.930, 0.90),
                (0.889, 0.800, 1.000, 1.00)
            ]
            runs = []
            for (name, desc, _), (f1, rec, prec, topo) in zip(configs_meta, static_scores):
                runs.append(AblationRunResult(
                    config_name=name,
                    description=desc,
                    best_f1=f1,
                    event_recall=rec,
                    event_precision=prec,
                    topology_score=topo
                ))
            analysis = (
                f"[ДЕМОНСТРАЦИОННЫЙ СЦЕНАРИЙ: статические демонстрационные показатели; реальный запуск выполняется с execute_live=True]\n"
                f"Абляционный анализ для Главы {gold_chapter.chapter_ordinal}:\n"
                f"1. B0 baseline: F1={static_scores[0][0]}, Recall={static_scores[0][1]}, Precision={static_scores[0][2]}.\n"
                f"2. Config A retrieval: F1={static_scores[1][0]}, Recall={static_scores[1][1]}, Precision={static_scores[1][2]}.\n"
                f"3. Config B canon: F1={static_scores[2][0]}, Recall={static_scores[2][1]}, Precision={static_scores[2][2]}.\n"
                f"4. Config C full: F1={static_scores[3][0]}, Recall={static_scores[3][1]}, Precision={static_scores[3][2]}."
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
                event_recall=report.oracle_at_k.event_recall,
                event_precision=report.oracle_at_k.event_precision,
                topology_score=report.oracle_at_k.topology_score
            ))

        analysis = (
            f"[ЭКСПЕРИМЕНТАЛЬНЫЙ ЗАПУСК: эмпирически измеренные показатели для Главы {gold_chapter.chapter_ordinal}]\n"
            f"1. B0 baseline: F1={runs[0].best_f1}, Recall={runs[0].event_recall}\n"
            f"2. Config A retrieval: F1={runs[1].best_f1}, Recall={runs[1].event_recall}\n"
            f"3. Config B canon: F1={runs[2].best_f1}, Recall={runs[2].event_recall}\n"
            f"4. Config C full: F1={runs[3].best_f1}, Recall={runs[3].event_recall}"
        )

        return AblationBenchmarkReport(
            test_chapter=gold_chapter.chapter_ordinal,
            runs=runs,
            summary_analysis=analysis,
            is_synthetic_demonstration=False
        )

