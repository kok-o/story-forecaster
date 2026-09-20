from abc import ABC, abstractmethod
from typing import Dict, Any, List
from ..domain.scope import ForecastScope
from ..domain.forecast import ForecastResult, PredictionCandidate
from ..domain.canon import ReferenceClassification

class ProviderUnavailableError(RuntimeError):
    """Raised when an explicitly requested LLM provider is unavailable."""
    pass

class BaseLLMProvider(ABC):
    """Abstract interface for LLM operations in the pipeline."""

    @abstractmethod
    def generate_hypotheses(
        self,
        scope: ForecastScope,
        target_context: Dict[str, Any],
        author_precedents: List[Dict[str, Any]],
        canon_context: List[Dict[str, Any]],
        num_candidates: int = 3
    ) -> ForecastResult:
        """Generates prospective chapter candidates within the scope boundaries."""
        pass

    @abstractmethod
    def classify_reference(self, entity_text: str, context_sentence: str) -> ReferenceClassification:
        """Classifies a potential cross-fandom reference."""
        pass
