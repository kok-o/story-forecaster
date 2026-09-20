import os
import json
from typing import Dict, Any, List, Optional
from .base import BaseLLMProvider
from ..domain.scope import ForecastScope
from ..domain.forecast import ForecastResult, PredictionCandidate
from ..domain.canon import ReferenceClassification

class GeminiProvider(BaseLLMProvider):
    """
    Adapter for Google Gemini API (gemini-3.8-flash).
    Requires GEMINI_API_KEY and google-genai package.
    """

    def __init__(self, api_key: Optional[str] = None):
        from story_forecaster.config import get_settings
        llm_cfg = get_settings().get("llm", {})
        api_env = llm_cfg.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = api_key or os.getenv(api_env) or os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL") or llm_cfg.get("model", "gemini-3.8-flash")
        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                # google-genai not installed
                self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    def classify_reference(self, entity_text: str, context_sentence: str) -> ReferenceClassification:
        if not self.is_available():
            raise RuntimeError("Gemini provider requested, but GEMINI_API_KEY is missing or google-genai is not installed.")
        prompt = f"Classify this fiction reference into CANONICAL_ELEMENT, FANON_TROPICAL, or DEFEASIBLE_OVERLAY:\nEntity: {entity_text}\nContext: {context_sentence}"
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        data = json.loads(response.text)
        return ReferenceClassification(data.get("classification", "AMBIGUOUS"))

    def build_forecast_prompt(
        self,
        scope: ForecastScope,
        target_context: Dict[str, Any],
        author_precedents: List[Dict[str, Any]],
        canon_context: List[Dict[str, Any]],
        num_candidates: int = 3
    ) -> tuple[str, str]:
        """Builds system instruction and prompt payload containing all narrative inputs."""
        cutoff_chapter = target_context.get("chapter_num", scope.target_max_discourse_seq)
        system_instruction = (
            "You are an expert literary narrative forecasting analyst. Your task is to generate plausible, "
            "diverse, and internally consistent narrative continuation hypotheses for the upcoming chapter "
            "of an ongoing novel.\n"
            "CRITICAL CONSTRAINTS (ZERO-FUTURE-LEAKAGE):\n"
            f"1. You must ONLY use facts from before discourse sequence {scope.target_max_discourse_seq}.\n"
            "2. Characters not yet introduced in the provided state must NEVER appear.\n"
            "3. Epistemic limits must be respected: characters cannot act on information they do not possess.\n"
            "4. Adhere strictly to the provided canon divergence rules and authorial decision precedents."
        )

        prompt_blocks = [
            f"=== WORK METADATA & SCOPE ===",
            f"Work Version ID: {scope.target_work_version_id}",
            f"Cutoff Chapter: {cutoff_chapter}",
            f"Discourse Sequence Boundary: <= {scope.target_max_discourse_seq}",
            f"Manifest Hash: {scope.manifest_hash()}",
            "",
            f"=== CURRENT NARRATIVE SNAPSHOT (POINT-IN-TIME) ===",
            f"Active Characters: {json.dumps(target_context.get('characters', []), ensure_ascii=False)}",
            f"World Conditions: {json.dumps(target_context.get('world_conditions', {}), ensure_ascii=False)}",
            f"Active Plot Threads: {json.dumps(target_context.get('active_threads', []), ensure_ascii=False)}",
            f"Epistemic Knowledge States: {json.dumps(target_context.get('epistemic_states', []), ensure_ascii=False)}",
            "",
            f"=== RECENT NARRATIVE CONTEXT PRECEDING CUTOFF ===",
            json.dumps(target_context.get("recent_scenes", []), ensure_ascii=False, indent=2),
            "",
            f"=== RETRIEVED HISTORICAL SCENES ===",
            json.dumps(target_context.get("retrieved_excerpts", []), ensure_ascii=False, indent=2),
            "",
            f"=== CANON OVERLAYS & DIVERGENCES ===",
            json.dumps(canon_context, ensure_ascii=False, indent=2),
            "",
            f"=== AUTHORIAL DECISION PRECEDENTS ===",
            json.dumps(author_precedents, ensure_ascii=False, indent=2),
            "",
            f"=== TASK ===",
            f"Generate exactly {num_candidates} distinct prospective continuation hypotheses for Chapter {int(cutoff_chapter) + 1}.",
            "Follow the ForecastResult JSON schema strictly."
        ]

        return system_instruction, "\n".join(prompt_blocks)

    def generate_hypotheses(
        self,
        scope: ForecastScope,
        target_context: Dict[str, Any],
        author_precedents: List[Dict[str, Any]],
        canon_context: List[Dict[str, Any]],
        num_candidates: int = 3
    ) -> ForecastResult:
        if not self.is_available():
            raise RuntimeError(
                "Gemini provider requested, but GEMINI_API_KEY is not configured or google-genai is not installed. "
                "Configure GEMINI_API_KEY or use provider='demo' for synthetic demonstration."
            )

        system_instruction, prompt = self.build_forecast_prompt(
            scope=scope,
            target_context=target_context,
            author_precedents=author_precedents,
            canon_context=canon_context,
            num_candidates=num_candidates
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": ForecastResult,
                "system_instruction": system_instruction
            }
        )

        result = ForecastResult.model_validate_json(response.text)
        result.provider = self.model_name
        result.is_synthetic_demonstration = False
        result.scope_manifest_hash = scope.manifest_hash()
        return result

