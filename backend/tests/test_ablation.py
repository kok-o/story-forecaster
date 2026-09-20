from story_forecaster.evaluation.ablation import AblationBenchmark

def test_ablation_benchmark_runs():
    bench = AblationBenchmark()
    report = bench.run_benchmark(cutoff_chapter=22)

    assert report.test_chapter == 23
    assert len(report.runs) == 4
    assert report.is_synthetic_demonstration is True
    
    # B0 baseline has lowest F1
    b0 = next(r for r in report.runs if r.config_name == "B0_baseline")
    assert b0.best_f1 <= 0.65

    # Config C full system has highest F1 and precision
    c_full = next(r for r in report.runs if r.config_name == "Config_C_full")
    assert c_full.best_f1 >= 0.85
    assert c_full.event_precision == 1.0
    assert c_full.topology_score == 1.0

    # Summary contains detailed component impact
    assert "Абляционный анализ" in report.summary_analysis
    assert "Recall" in report.summary_analysis
    assert "Precision" in report.summary_analysis

def test_live_ablation_benchmark_runs():
    bench = AblationBenchmark()
    report = bench.run_benchmark(cutoff_chapter=22, execute_live=True)
    assert report.test_chapter == 23
    assert len(report.runs) == 4
    assert report.is_synthetic_demonstration is False
    for r in report.runs:
        assert 0.0 <= r.best_f1 <= 1.0

