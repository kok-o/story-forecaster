from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field

class AppConfig(BaseModel):
    name: str = "Story Forecaster"
    version: str = "1.0.0"
    mode: str = "local"
    source_language: str = "ru"
    default_output_language: str = "ru"
    public_access: bool = False

class TaskProfileConfig(BaseModel):
    thinking: str = "medium"
    output_cap: int = 8192

class LLMConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-3.8-flash"
    api_key_env: str = "GEMINI_API_KEY"
    concurrency: int = 2
    timeout_seconds: int = 180
    transport_attempts: int = 3
    semantic_repair_attempts: int = 1
    task_profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

class RetrievalConfig(BaseModel):
    lexical_backend: str = "bm25"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    dense_top_k: int = 30
    lexical_top_k: int = 30
    rerank_pool: int = 60
    rrf_k: int = 60
    strict_backtest_search: str = "exact"

class ForecastConfig(BaseModel):
    input_soft_cap_tokens: int = 28000
    topology_candidates: int = 3
    plans_per_topology: int = 2
    final_candidates_max: int = 5
    min_desired_candidates: int = 3
    events_per_candidate_min: int = 3
    events_per_candidate_max: int = 6
    repair_rounds: int = 1

class EvaluationConfig(BaseModel):
    live_web: bool = False
    repeated_samples: int = 3
    reuse_generation_cache: bool = False

class AppSettings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)

    def get(self, key: str, default: Any = None) -> Any:
        """Backwards compatibility for dict-like access."""
        if hasattr(self, key):
            val = getattr(self, key)
            if isinstance(val, BaseModel):
                return val.model_dump()
            return val
        return default

    def __getitem__(self, item: str) -> Any:
        res = self.get(item)
        if res is None:
            raise KeyError(item)
        return res

_SETTINGS_CACHE: Optional[AppSettings] = None

def get_settings(reload: bool = False) -> AppSettings:
    """Loads, validates, and caches settings from config/settings.yaml."""
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None and not reload:
        return _SETTINGS_CACHE

    candidates = [
        Path(__file__).resolve().parents[3] / "config" / "settings.yaml",
        Path.cwd() / "config" / "settings.yaml",
        Path("config/settings.yaml").resolve()
    ]

    raw_data: Dict[str, Any] = {}
    for p in candidates:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if isinstance(loaded, dict):
                        raw_data = loaded
                        break
            except Exception:
                pass

    try:
        _SETTINGS_CACHE = AppSettings.model_validate(raw_data)
    except Exception:
        _SETTINGS_CACHE = AppSettings()

    return _SETTINGS_CACHE
