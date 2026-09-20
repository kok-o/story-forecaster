import os
import sys
import json
from typing import Optional

# Reconfigure stdout/stderr for UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console(force_terminal=True, legacy_windows=False)

# Add src to path
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from story_forecaster.ingestion.importer import import_target_work
from story_forecaster.db import SessionLocal, Project, Work, WorkVersion, Chapter, Scene, Run, Candidate
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.providers import get_provider, ProviderUnavailableError
from story_forecaster.config import get_settings
from story_forecaster.domain.resolver import resolve_scope

app = typer.Typer(help="Story Forecaster CLI for Author N.B. and 'Система Абсолютного З.Л.А.'")
console = Console()

@app.command()
def doctor(
    probe_api: bool = typer.Option(False, "--probe-api", help="Perform live Gemini API probe if GEMINI_API_KEY is configured")
):
    """Diagnoses system readiness: checks configuration, database, directories, meta-corpus, frontend, and providers."""
    from pathlib import Path
    
    console.print(Panel.fit(
        "[bold cyan]Story Forecaster System Health & Readiness Doctor[/bold cyan]\n"
        "Verifying dependencies, configuration, database integrity, file corpus, and forecast pipelines...",
        border_style="cyan"
    ))
    
    table = Table(title="Диагностическая сводка системы")
    table.add_column("Компонент", style="cyan")
    table.add_column("Статус", style="bold")
    table.add_column("Детализация", style="white")

    has_critical_error = False

    # 1. Python environment
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    table.add_row("Python Environment", "[green]OK[/green]", f"Python {py_ver} ({sys.platform})")

    # 2. Configuration & Schema validation
    settings = None
    try:
        settings = get_settings(reload=True)
        table.add_row(
            "Configuration (settings.yaml)",
            "[green]OK[/green]",
            f"Validated via Pydantic: mode={settings.app.mode}, model={settings.llm.model}, timeout={settings.llm.timeout_seconds}s"
        )
    except Exception as e:
        table.add_row("Configuration (settings.yaml)", "[red]FAILED[/red]", f"Validation error: {e}")
        has_critical_error = True

    project_root = Path(__file__).resolve().parents[3]

    # 3. Database & Schema
    db_ok = False
    try:
        db = SessionLocal()
        work = db.query(Work).filter_by(role="target").first()
        ch_count = db.query(Chapter).count()
        sc_count = db.query(Scene).count()
        cand_count = db.query(Candidate).count()
        db.close()
        db_ok = True
        db_details = f"Target: '{work.title if work else 'None'}', Chapters: {ch_count}, Scenes: {sc_count}, Candidates: {cand_count}"
        table.add_row("Database (SQLite/ORM)", "[green]OK[/green]", db_details)
    except Exception as e:
        table.add_row("Database (SQLite/ORM)", "[red]FAILED[/red]", str(e))
        has_critical_error = True

    # 4. Chapters directory & manifest
    target_dir = project_root / "data" / "target" / "chapters"
    manifest_file = target_dir / "manifest.json"
    if manifest_file.exists():
        files_count = len(list(target_dir.glob("chapter_*.txt")))
        table.add_row("Target Corpus (Chapters)", "[green]OK[/green]", f"{files_count} chapters in {target_dir.name} (manifest present)")
    else:
        table.add_row("Target Corpus (Chapters)", "[yellow]WARNING[/yellow]", f"Missing manifest at {manifest_file}")

    # 5. Meta-Corpus FB2 directories
    meta_folders = [
        "NB-neudacha",
        "NB-obnovlennyy-mir",
        "NB - 1 - Смертельная Игра",
        "NB - Картежник",
        "NB - По ту сторону Врат"
    ]
    found_meta = [f for f in meta_folders if (project_root / f).exists()]
    if len(found_meta) == len(meta_folders):
        table.add_row("Meta-Corpus (N.B. 13 FB2)", "[green]OK[/green]", f"All {len(found_meta)} cycles found (~20M chars)")
    else:
        table.add_row("Meta-Corpus (N.B. 13 FB2)", "[yellow]PARTIAL[/yellow]", f"Found {len(found_meta)}/{len(meta_folders)} cycles")

    # 6. Frontend assets
    frontend_dir = project_root / "frontend"
    has_html = (frontend_dir / "index.html").exists()
    has_js = (frontend_dir / "app.js").exists()
    has_css = (frontend_dir / "styles.css").exists()
    if has_html and has_js and has_css:
        table.add_row("Web UI Frontend", "[green]OK[/green]", "Dark-mode Glassmorphism SPA ready (HTML/CSS/JS)")
    else:
        table.add_row("Web UI Frontend", "[red]MISSING[/red]", "Incomplete frontend assets")

    # 7. Provider status & real network probe
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    if probe_api:
        if has_key:
            try:
                from google import genai
                client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
                model_name = settings.llm.model if settings else "gemini-3.8-flash"
                client.models.generate_content(
                    model=model_name,
                    contents="Ping. Respond with 'PONG'."
                )
                table.add_row("LLM Provider Probe", "[green]VERIFIED[/green]", f"Live API probe passed (model: {model_name})")
            except Exception as e:
                table.add_row("LLM Provider Probe", "[red]FAILED[/red]", f"Live API probe error: {e}")
                has_critical_error = True
        else:
            table.add_row("LLM Provider Probe", "[yellow]SKIPPED[/yellow]", "GEMINI_API_KEY not set in environment (cannot probe live API)")
    else:
        if has_key:
            table.add_row("LLM Provider Default", "[green]CONFIGURED[/green]", "GEMINI_API_KEY detected in environment")
        else:
            table.add_row("LLM Provider Default", "[yellow]OFFLINE DEMO[/yellow]", "DemoProvider active (offline deterministic fixtures)")

    console.print(table)
    if has_critical_error:
        console.print("[bold red]System health check failed: Please resolve critical errors above.[/bold red]\n")
        raise typer.Exit(code=1)
    else:
        console.print("[bold green]System check completed: Ready for forecast, backtest, and ablation pipelines.[/bold green]\n")

@app.command()
def ingest(
    manifest: str = typer.Option("data/target/chapters/manifest.json", help="Path to chapters manifest.json")
):
    """Ingests and indexes chapters and scenes into the database."""
    console.print(f"[bold cyan]Ingesting work from {manifest}...[/bold cyan]")
    res = import_target_work(manifest_path=manifest)
    console.print(f"[bold green]Success![/bold green] Ingested {res['total_chapters']} chapters, {res['total_scenes']} scenes.")
    console.print(f"Project ID: [yellow]{res['project_id']}[/yellow]")

@app.command()
def inspect(
    chapter: Optional[int] = typer.Option(None, help="Inspect state up to a specific chapter")
):
    """Inspects indexed chapters, scenes, and current plot status."""
    db = SessionLocal()
    try:
        try:
            resolved = resolve_scope(db)
        except ValueError as e:
            console.print(f"[red]No target work found: {e}. Run 'python -m story_forecaster.cli ingest' first.[/red]")
            return

        work = resolved.work
        version = resolved.version
        chapters = db.query(Chapter).filter_by(work_version_id=version.id).order_by(Chapter.ordinal).all()
        table = Table(title=f"{work.title} ({work.author_name}) [версия {version.id[:8]}] - Оглавление и сцены")
        table.add_column("№", justify="right", style="cyan")
        table.add_column("Заголовок", style="white")
        table.add_column("Символов", justify="right", style="green")
        table.add_column("Сцен", justify="right", style="yellow")
        table.add_column("Диапазон discourse_seq", justify="center", style="magenta")

        for ch in chapters:
            scenes = db.query(Scene).filter_by(chapter_id=ch.id).order_by(Scene.discourse_seq).all()
            sc_count = len(scenes)
            seq_range = f"{scenes[0].discourse_seq} - {scenes[-1].discourse_seq}" if scenes else "N/A"
            table.add_row(str(ch.ordinal), ch.title, f"{ch.char_count:,}", str(sc_count), seq_range)

        console.print(table)
    finally:
        db.close()

@app.command()
def forecast(
    cutoff_chapter: int = typer.Option(23, help="Forecast continuation after this chapter"),
    provider_name: str = typer.Option("demo", help="Provider: 'demo', 'gemini', or 'auto'")
):
    """Generates 3-5 prospective chapter candidates honoring zero-leakage scope."""
    db = SessionLocal()
    try:
        try:
            resolved = resolve_scope(db, cutoff_chapter=cutoff_chapter)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        scope = resolved.scope
        console.print(Panel.fit(
            f"[bold cyan]Story Forecaster Engine[/bold cyan]\n"
            f"Произведение: [yellow]{resolved.work.title}[/yellow]\n"
            f"Версия: [cyan]{resolved.version.id}[/cyan]\n"
            f"Точка отсечки: [green]Конец главы {cutoff_chapter} (discourse_seq <= {resolved.max_discourse_seq})[/green]\n"
            f"Провайдер: [magenta]{provider_name}[/magenta]",
            border_style="cyan"
        ))

        from story_forecaster.forecast.engine import ForecastEngine
        try:
            provider = get_provider(provider_name=provider_name)
        except ProviderUnavailableError as e:
            console.print(f"[bold red]Ошибка провайдера:[/bold red] {e}")
            raise typer.Exit(code=1)

        engine = ForecastEngine(provider=provider)
        result = engine.run_forecast(scope=scope, num_candidates=3, persist_run=True)

        for idx, cand in enumerate(result.candidates, start=1):
            console.print(f"\n[bold yellow]═══ ВАРИАНТ {idx}: {cand.title} ═══[/bold yellow]")
            console.print(f"• [bold]POV[/bold]: [cyan]{cand.topology.pov_character}[/cyan] | [bold]Режим[/bold]: [magenta]{cand.topology.narrative_mode.value}[/magenta] | [bold]Темп[/bold]: {cand.topology.estimated_pacing}")
            console.print(f"• [bold]Уверенность[/bold]: [green]{cand.confidence_label}[/green]")
            console.print(f"• [bold]Обоснование[/bold]: {cand.rationale}")
            
            console.print("• [bold]Основные сюжетные ходы (Beats):[/bold]")
            for b in cand.key_events:
                console.print(f"   [cyan]{b.ordinal}.[/cyan] {b.summary} [dim]({b.conflict_type})[/dim]")
                
            if cand.potential_twist:
                console.print(f"• [bold red]Возможный поворот / клиффхэнгер[/bold red]: {cand.potential_twist}")

    finally:
        db.close()

@app.command()
def canon():
    """Inspects the 5-state defeasible canon alignment for Highschool of the Dead."""
    from story_forecaster.canon.registry import CanonDivergenceRegistry
    registry = CanonDivergenceRegistry()
    scope = ForecastScope(
        project_id="default",
        target_work_version_id="target_v1",
        target_max_discourse_seq=192
    )
    summary = registry.get_divergence_summary(scope)

    console.print(Panel.fit(
        f"[bold cyan]5-Статусный Реестр Канона HOTD ('Школа Мертвецов')[/bold cyan]\n"
        f"Всего отслеживаемых элементов: [yellow]{summary['total_canon_elements_tracked']}[/yellow]\n"
        f"Распределение: [green]MODIFIED: {summary['distribution']['MODIFIED']}[/green] | "
        f"[yellow]DEPENDS: {summary['distribution']['DEPENDS_ON_CHANGED_CONDITIONS']}[/yellow] | "
        f"[blue]PRESUMED_INTACT: {summary['distribution']['PRESUMED_INTACT']}[/blue]",
        border_style="cyan"
    ))

    table = Table(title="Канонические элементы и их статус в фанфике")
    table.add_column("ID Элемента", style="cyan")
    table.add_column("Событие/Персонаж", style="white")
    table.add_column("Статус отношения", style="yellow")
    table.add_column("Причинность", style="magenta")
    table.add_column("Основания и заметки", style="dim")

    for el in summary["elements"]:
        table.add_row(
            el["element_id"],
            el["description"],
            el["canon_relation"],
            el["dependency_status"],
            el.get("notes") or ""
        )

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (e.g. 'Хорадримский Куб', 'пыльца фей')"),
    cutoff_chapter: int = typer.Option(23, help="Max chapter cutoff to search through"),
    top_k: int = typer.Option(5, help="Number of results to return")
):
    """Executes a hybrid BM25 + dense search over permitted story scenes with strict zero future leakage."""
    db = SessionLocal()
    try:
        try:
            resolved = resolve_scope(db, cutoff_chapter=cutoff_chapter)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        from story_forecaster.retrieval import HybridRetrievalEngine
        engine = HybridRetrievalEngine(db_session=db)
        results = engine.search(query=query, scope=resolved.scope, top_k=top_k)

        console.print(Panel.fit(
            f"[bold cyan]Hybrid Scope Search[/bold cyan]\n"
            f"Запрос: [yellow]{query}[/yellow]\n"
            f"Версия: [cyan]{resolved.version.id}[/cyan]\n"
            f"Граница отсечки: [green]Конец главы {cutoff_chapter} (discourse_seq <= {resolved.max_discourse_seq})[/green]\n"
            f"Найдено релевантных сцен: [magenta]{len(results)}[/magenta]",
            border_style="cyan"
        ))

        table = Table(title=f"Результаты поиска по запросу: '{query}'")
        table.add_column("№", justify="right", style="cyan")
        table.add_column("Гл.", justify="right", style="yellow")
        table.add_column("Seq", justify="center", style="magenta")
        table.add_column("RRF Score", justify="right", style="green")
        table.add_column("Фрагмент текста", style="white")

        for idx, r in enumerate(results, start=1):
            table.add_row(
                str(idx),
                str(r.chapter_num),
                str(r.discourse_seq),
                f"{r.score:.4f}",
                r.content_snippet
            )

        console.print(table)
    finally:
        db.close()

@app.command()
def backtest(
    cutoff_chapter: int = typer.Option(22, help="Cutoff chapter (forecasts chapter cutoff+1 as hidden test)"),
    provider_name: str = typer.Option("demo", help="Provider: 'demo', 'gemini', or 'auto'")
):
    """Executes a blind backtest comparing forecasted candidates against held-out gold chapter events."""
    db = SessionLocal()
    try:
        try:
            resolved = resolve_scope(db, cutoff_chapter=cutoff_chapter)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        hidden_chapter_num = cutoff_chapter + 1
        from story_forecaster.evaluation import get_gold_chapter, BacktestEvaluator
        try:
            gold = get_gold_chapter(hidden_chapter_num)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        console.print(Panel.fit(
            f"[bold cyan]Story Forecaster Backtest Benchmark[/bold cyan]\n"
            f"Произведение: [yellow]{resolved.work.title}[/yellow]\n"
            f"Версия: [cyan]{resolved.version.id}[/cyan]\n"
            f"Граница разрешенного контекста: [green]Конец главы {cutoff_chapter} (discourse_seq <= {resolved.max_discourse_seq})[/green]\n"
            f"Скрытая тестируемая глава: [bold magenta]Глава {hidden_chapter_num}[/bold magenta]\n"
            f"Провайдер: [magenta]{provider_name}[/magenta]",
            border_style="cyan"
        ))

        from story_forecaster.forecast.engine import ForecastEngine
        try:
            provider = get_provider(provider_name=provider_name)
        except ProviderUnavailableError as e:
            console.print(f"[bold red]Ошибка провайдера:[/bold red] {e}")
            raise typer.Exit(code=1)

        engine = ForecastEngine(provider=provider)
        result = engine.run_forecast(scope=resolved.scope, num_candidates=3, persist_run=True)

        evaluator = BacktestEvaluator()
        report = evaluator.evaluate_forecast(result, gold, cutoff_chapter=cutoff_chapter)

        table = Table(title=f"Результаты бэктеста: Прогноз Главы {hidden_chapter_num} по Главам 1-{cutoff_chapter}")
        table.add_column("Кандидат", style="cyan")
        table.add_column("POV / Режим", style="white")
        table.add_column("Топология", justify="center", style="yellow")
        table.add_column("Precision", justify="right", style="green")
        table.add_column("Recall", justify="right", style="magenta")
        table.add_column("F1", justify="right", style="bold green")

        for cand_m in report.all_candidates:
            table.add_row(
                cand_m.title,
                f"{cand_m.pov_character} ({cand_m.narrative_mode})",
                f"{cand_m.topology_score:.1f}",
                f"{cand_m.event_precision:.3f}",
                f"{cand_m.event_recall:.3f}",
                f"{cand_m.event_f1:.3f}"
            )

        console.print(table)

        console.print(Panel.fit(
            f"[bold]Best@1 (Основной прогноз):[/bold] F1=[bold green]{report.best_at_1.event_f1}[/bold green] "
            f"(Recall={report.best_at_1.event_recall}, Precision={report.best_at_1.event_precision})\n"
            f"[bold]Oracle@{report.total_candidates} (Лучший из луча):[/bold] F1=[bold green]{report.oracle_at_k.event_f1}[/bold green] "
            f"(Кандидат: '{report.oracle_at_k.title}')\n"
            f"[bold]Средний F1 (Mean):[/bold] {report.mean_f1}",
            title="Итоговые метрики (Benchmark Metrics)",
            border_style="green"
        ))

        match_table = Table(title=f"Детальное сопоставление событий (Кандидат: {report.oracle_at_k.title})")
        match_table.add_column("Эталонное событие (Gold)", style="white")
        match_table.add_column("Предсказанный ход (Beat)", style="cyan")
        match_table.add_column("Вес", justify="center", style="green")
        match_table.add_column("Обоснование совпадения", style="dim")

        for m in report.oracle_at_k.matches:
            weight_str = "[bold green]1.0[/bold green]" if m.weight == 1.0 else f"[yellow]{m.weight}[/yellow]"
            match_table.add_row(
                m.gold_summary,
                m.predicted_summary,
                weight_str,
                m.rationale
            )

        console.print(match_table)
    finally:
        db.close()

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host address to bind to"),
    port: int = typer.Option(8000, help="Port to listen on")
):
    """Starts the FastAPI REST server for Story Forecaster."""
    import uvicorn
    console.print(Panel.fit(
        f"[bold cyan]Story Forecaster REST API Server[/bold cyan]\n"
        f"URL: [green]http://{host}:{port}[/green]\n"
        f"Docs: [yellow]http://{host}:{port}/docs[/yellow]",
        border_style="cyan"
    ))
    uvicorn.run("story_forecaster.api.main:app", host=host, port=port, reload=False)

@app.command()
def ablation():
    """Runs component ablation benchmark comparing B0, Config A, Config B, and Full Config C."""
    from story_forecaster.evaluation.ablation import AblationBenchmark
    bench = AblationBenchmark()
    report = bench.run_benchmark()

    table = Table(title=f"Абляционный бенчмарк архитектуры (Тестовая глава {report.test_chapter})")
    table.add_column("Конфигурация", style="cyan")
    table.add_column("Описание компонентов", style="white")
    table.add_column("F1", justify="right", style="bold green")
    table.add_column("Recall", justify="right", style="magenta")
    table.add_column("Precision", justify="right", style="yellow")
    table.add_column("Топология", justify="right", style="cyan")

    for r in report.runs:
        table.add_row(
            r.config_name,
            r.description,
            f"{r.best_f1:.3f}",
            f"{r.event_recall:.3f}",
            f"{r.event_precision:.3f}",
            f"{r.topology_score:.2f}"
        )

    console.print(table)
    console.print(Panel.fit(report.summary_analysis, title="Аналитическое заключение", border_style="green"))

@app.command()
def update(
    file_path: str = typer.Option(..., "--file", "-f", help="Path to new chapter text or markdown file"),
    title: Optional[str] = typer.Option(None, help="Optional chapter title"),
    ordinal: Optional[int] = typer.Option(None, help="Optional chapter ordinal number")
):
    """Incrementally ingests a newly published chapter into the database without reindexing all chapters."""
    from story_forecaster.ingestion.updater import IncrementalChapterUpdater
    with open(file_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    updater = IncrementalChapterUpdater()
    res = updater.update_chapter(raw_text=raw_text, title=title, ordinal=ordinal)

    console.print(Panel.fit(
        f"[bold green]Глава успешно добавлена в корпус![/bold green]\n"
        f"Номер главы: [cyan]{res['chapter_ordinal']}[/cyan] ({res['chapter_title']})\n"
        f"Знаков: [yellow]{res['char_count']:,}[/yellow]\n"
        f"Выделено сцен: [magenta]{res['scenes_count']}[/magenta]\n"
        f"Диапазон дискурса: [green]discourse_seq: {res['discourse_seq_start']} – {res['discourse_seq_end']}[/green]",
        title="Incremental Ingestion Complete",
        border_style="cyan"
    ))

if __name__ == "__main__":
    app()


