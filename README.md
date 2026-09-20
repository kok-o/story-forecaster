# Story Forecaster — Исследовательская система сюжетного прогнозирования

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg" alt="Python Versions" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Pydantic-v2.7%2B-e92063.svg" alt="Pydantic" />
  <img src="https://img.shields.io/badge/LLM-Gemini%203.8%20Flash-4285F4.svg" alt="Gemini" />
  <img src="https://img.shields.io/badge/Tests-43%20Passing-brightgreen.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
</p>

---

## 🌐 English Abstract

**Story Forecaster** is a neuro-symbolic narrative intelligence system engineered for prospective story forecasting, narrative structure modeling, and leak-free plot hypothesis generation for ongoing serial novels.

Traditional large language models suffer from severe epistemic drift (characters acting on omniscient knowledge), canon hallucination, and timeline leakage when tasked with story continuation. Story Forecaster bridges **Symbolic AI** (immutable scope contracts, Theory of Mind memory graphs, defeasible canon ontologies) with **Generative LLMs (Google Gemini 3.8 Flash)** and **Hybrid BM25/RRF Retrieval** to formulate testable, consistent, and ranked narrative continuation hypotheses.

* **Target Corpus:** Web novel *«Система Абсолютного З.Л.А.»* by author **N.B.** (~1.12M chars, crossover: *Highschool of the Dead* + *KonoSuba* + *Diablo* mechanics) and a 13-book authorial meta-corpus (~20M chars).
* **Core Principles:** Zero Future Leakage, Defeasible Canon Alignment, Theory of Mind, Bipartite Matching Backtesting.

---

## 📖 Описание проекта (Russian)

**Story Forecaster** — инженерно-аналитический комплекс для глубокого анализа нарративных структур, отслеживания динамики сюжетных линий и формирования проверяемых гипотез развития незавершённого литературного произведения.

Система разработана на материале романа **«Система Абсолютного З.Л.А.»** автора **N.B.** (основной мир: *Highschool of the Dead*; кроссовер: *KonoSuba*, механика *Хорадримского Куба Diablo*, мультивселенная осколков).

Полный технический аудит архитектуры: [docs/project_audit_2026-09-20.md](docs/project_audit_2026-09-20.md).  
Архитектурная спецификация: [docs/architecture.md](docs/architecture.md).

---

## 🚀 Архитектурные возможности

```mermaid
flowchart TD
    Scope["ForecastScope (discourse_seq <= cutoff)"] --> Memory["NarrativeMemoryEngine (Theory of Mind & Active Threads)"]
    Scope --> Canon["CanonDivergenceRegistry (5-State Defeasible Alignment)"]
    Scope --> Retrieval["HybridRetrievalEngine (BM25 + RRF k=60)"]
    MetaCorpus["Meta-Corpus (13 N.B. Books)"] --> Precedents["AuthorPrecedentLibrary (Tagged Authorial Tropes)"]

    Memory & Canon & Retrieval & Precedents --> Step1["Step 1: Macro-Topology Generator (POV, Mode, Pacing)"]
    Step1 --> Step2["Step 2: Micro-Beat Synthesizer (Gemini 3.8 Flash / JSON Schema)"]
    Step2 --> Verifier["Step 3: Continuity Guardrail (Anti-Leak & Epistemic Filter)"]
    Verifier --> Output["Ranked Hypotheses with Rationale & Continuity Status"]
```

1. **Изоляция версий и неизменяемый скоуп (*Zero Future Leakage*):**
   Контракт `ForecastScope` (замороженный `frozen=True` Pydantic-объект) фиксирует `project_id`, `target_work_version_id`, `target_max_discourse_seq` и полный `manifest_hash()`. Все запросы к базе данных, памяти и поисковому индексу изолированы в пределах границы отсечки.
2. **Историческая память сюжета (*NarrativeMemoryEngine* & *Theory of Mind*):**
   Точечный срез состояния мира на момент главы $N$: персонажи фильтруются по отсечке появления (персонажи будущих глав физически не попадают в срез), отслеживаются открытые сюжетные арки и эпистемические знания персонажей (кто что знает, и какие ложные убеждения активны).
3. **Опровержимое согласование канона (*Defeasible Canon Alignment*):**
   5-статусная модель канона (*MODIFIED*, *CONFIRMED*, *PRESUMED_INTACT* и др.) со смещением таймлайна (поступление протагониста за 1 год до канонического прорыва Данжа в Академии Фудзими).
4. **Гибридный поиск без утечек (*HybridRetrievalEngine*):**
   Полнотекстовый поиск BM25 ($k_1=1.2, b=0.75$) + лексическое пересечение + Reciprocal Rank Fusion ($RRF\ k=60$) со строгой фильтрацией по версии и $seq \le cutoff$.
5. **Двухуровневый LLM-контур прогнозирования:**
   * **Реальный LLM-контур (Google Gemini 3.8 Flash):** компилирует срез памяти, канонические правила и авторские прецеденты в структурированный промпт и валидирует ответ через строгую JSON-схему `ForecastResult`.
   * **Демонстрационный провайдер (`demo`):** автономный режим для тестов и локального запуска без API-ключа с явной маркировкой `is_synthetic_demonstration: True`.
6. **Символическая проверка непрерывности (*Continuity Verification*):**
   Автоматический фильтр отсеивает кандидатов с неинтродуцированными персонажами или нарушениями эпистемических ограничений героев.
7. **Объективный оценщик и бэктестинг (*BacktestEvaluator*):**
   Жадное двудольное сопоставление (*Greedy 1-to-1 Bipartite Matching*) предсказанных битов против фактического эталона (Gold Standard) с расчетом метрик *Precision*, *Recall*, *F1-score* и топологического соответствия.
8. **Абляционные исследования (*AblationBenchmark*):**
   Экспериментальное измерение вклада компонентов (памяти, поиска, канона, базы прецедентов) в итоговое качество прогноза.

---

## 📦 Быстрый старт (Quickstart)

### 1. Системные требования
* **Python 3.11+** (протестировано на Python 3.11, 3.12, 3.13)
* **SQLite 3**
* Операционная система: Windows, Linux или macOS

### 2. Клонирование и установка зависимостей
```bash
git clone https://github.com/kok-o/story-forecaster.git
cd story-forecaster

# Создание и активация виртуального окружения
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Настройка переменных окружения (опционально для Live LLM)
Скопируйте шаблон `.env.example` в `.env`:
```bash
cp .env.example .env
```
Укажите ваш API-ключ Gemini (получить бесплатно в [Google AI Studio](https://aistudio.google.com/)):
```ini
GEMINI_API_KEY=your_actual_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
PORT=8000
```
> *Примечание:* Если ключ не задан, система полноценно функционирует в демо-режиме (`--provider demo`) на встроенном калибровочном корпусе.

### 4. Запуск тестов
```bash
pytest
```
*Все 43 модульных и интеграционных теста запускаются в изолированной SQLite in-memory среде без изменения основной базы данных.*

### 5. Запуск Web UI и REST API
```bash
# Windows PowerShell:
$env:PYTHONPATH="backend/src"
python -m story_forecaster.cli serve --port 8000

# Linux / macOS:
PYTHONPATH="backend/src" python -m story_forecaster.cli serve --port 8000
```
После запуска откройте:
* **Web UI (Интерактивная панель):** [http://127.0.0.1:8000](http://127.0.0.1:8000)
* **REST API Документация (Swagger / OpenAPI):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🛠 Консольный интерфейс (CLI)

```bash
# Проверка конфигурации и целостности окружения
python -m story_forecaster.cli doctor

# Инспекция активной версии романа, отсечек и глав
python -m story_forecaster.cli inspect

# Генерация сюжетного прогноза после указанной главы
python -m story_forecaster.cli forecast --cutoff-chapter 23

# Слепой бэктест прогноза против эталона вышедшей главы
python -m story_forecaster.cli backtest --cutoff-chapter 22

# Запуск абляционного анализа архитектуры
python -m story_forecaster.cli ablation

# Гибридный поиск по сценам до границы отсечки
python -m story_forecaster.cli search "Хорадримский Куб" --cutoff-chapter 23
```

---

## 📂 Структура репозитория

```
story-forecaster/
├── backend/
│   ├── src/story_forecaster/
│   │   ├── api/          # FastAPI REST API (эндпоинты, статика)
│   │   ├── author/       # Библиотека прецедентов и стилистических тропов автора
│   │   ├── canon/        # 5-статусный реестр канона и кроссовер-онтология
│   │   ├── db/           # SQLAlchemy ORM, сессии SQLite
│   │   ├── domain/       # Pydantic v2 контракты (Scope, Candidate, Snapshot)
│   │   ├── evaluation/   # 1-to-1 Bipartite Matching оценщик и бэктестинг
│   │   ├── forecast/     # Двухэтапный конвейер сюжетного прогнозирования
│   │   ├── ingestion/    # Нормализаторы текстов, парсер глав, инкрементальный апдейтер
│   │   ├── memory/       # Редуктор сюжетного состояния, Theory of Mind
│   │   ├── providers/    # Двухуровневый LLM-шлюз (GeminiProvider + DemoProvider)
│   │   ├── retrieval/    # Гибридный поисковый движок (BM25 + RRF k=60)
│   │   └── cli.py        # Единая консоль управления Typer + Rich
│   └── tests/            # Набор из 43 модульных и интеграционных тестов
├── config/               # Конфигурационные файлы (settings.yaml, target_work.yaml)
├── data/                 # Локальная база данных SQLite и тестовые срезы глав
├── docs/                 # Документация, архитектурные схемы и спецификации
├── frontend/             # Легковесный Single Page Web UI (HTML/CSS/JS)
├── .env.example          # Шаблон переменных окружения
├── .gitignore            # Исключение кэшей, секретов и защищенных текстов
├── LICENSE               # Лицензия MIT
├── pyproject.toml        # Конфигурация сборки и тестов
└── requirements.txt      # Зависимости Python
```

---

## ⚖️ Дисклеймер об авторских правах (Academic & Fair Use Disclaimer)

Данное программное обеспечение является исследовательским инструментом в области компьютерной нарратологии (*Computational Narratology*) и искусственного интеллекта. Все упоминания сторонних художественных произведений, персонажей и выдержки из текстов используются исключительно в исследовательских, аналитических и тестировочных целях в рамках добросовестного использования (*Fair Use*). Авторские права на исходные тексты и вселенные принадлежат их законным правообладателям.

---

## 📄 Лицензия

Проект распространяется под открытой лицензией [MIT](LICENSE).
