import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from .base import BaseLLMProvider, ProviderUnavailableError
from ..domain.scope import ForecastScope
from ..domain.forecast import ForecastResult, PredictionCandidate
from ..domain.canon import ReferenceClassification

logger = logging.getLogger(__name__)

class GeminiProvider(BaseLLMProvider):
    """
    Production-ready adapter for Google Gemini API (gemini-2.5-flash / gemini-3.8-flash).
    Adheres strictly to M2 requirements:
    1. Zero silent fallback to demo; explicit ProviderUnavailableError.
    2. Segregated source documents and control instructions.
    3. Full JSON schema passed in instructions and enforced locally.
    4. Exponential backoff and retry loop for transient network/rate errors.
    5. Usage metadata capture and zero secret leakage.
    """

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3, timeout_seconds: int = 60):
        from story_forecaster.config import get_settings
        llm_cfg = get_settings().get("llm", {})
        api_env = llm_cfg.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = api_key or os.getenv(api_env) or os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL") or llm_cfg.get("model", "gemini-2.5-flash")
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    def classify_reference(self, entity_text: str, context_sentence: str) -> ReferenceClassification:
        if not self.is_available():
            raise ProviderUnavailableError(
                "Gemini provider is unavailable because GEMINI_API_KEY is missing or google-genai is not installed."
            )
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
        """
        Builds system instruction and prompt payload containing all narrative inputs.
        Strictly segregates source documents from control instructions and supplies the explicit schema.
        """
        cutoff_chapter = target_context.get("chapter_num", scope.target_max_discourse_seq)

        system_instruction = (
            "You are an expert literary narrative forecasting analyst. Your task is to generate plausible, "
            "diverse, and internally consistent narrative continuation hypotheses for the upcoming chapter "
            "of an ongoing novel.\n\n"
            "CRITICAL CONSTRAINTS (ZERO-FUTURE-LEAKAGE):\n"
            f"1. You must ONLY use facts established in the provided <source_documents> (discourse sequence <= {scope.target_max_discourse_seq}).\n"
            "2. Characters not yet introduced in the provided state must NEVER appear.\n"
            "3. Epistemic limits must be respected: characters cannot act on information they do not possess.\n"
            "4. CITATION INTEGRITY: In every PlotBeat or candidate citing evidence, reference ONLY valid source IDs "
            "from <source_documents> (e.g. 'scene_191'). Fictitious or future source citations will cause immediate rejection.\n"
            "5. Adhere strictly to the provided authorial decision precedents and canon divergence rules."
        )

        # 1. Source documents block
        formatted_sources = target_context.get("formatted_source_text")
        if not formatted_sources:
            scenes_raw = target_context.get("recent_scenes", [])
            doc_blocks = []
            for sc in scenes_raw:
                s_id = f"scene_{sc.get('discourse_seq', 0)}"
                content_text = sc.get("content") or sc.get("snippet") or sc.get("summary") or ""
                doc_blocks.append(
                    f'<source id="{s_id}" chapter="{sc.get("chapter_ordinal", "?")}" seq="{sc.get("discourse_seq", "?")}">\n'
                    f'{content_text}\n'
                    f'</source>'
                )
            formatted_sources = "<source_documents>\n" + "\n\n".join(doc_blocks) + "\n</source_documents>"

        retrieved_raw = target_context.get("retrieved_excerpts", [])
        if retrieved_raw:
            rx_blocks = []
            for rx in retrieved_raw:
                rx_blocks.append(
                    f'<retrieved_excerpt chapter="{rx.get("chapter_ordinal", "?")}">\n'
                    f'{rx.get("snippet", "")}\n'
                    f'</retrieved_excerpt>'
                )
            formatted_sources += "\n\n<retrieved_historical_excerpts>\n" + "\n\n".join(rx_blocks) + "\n</retrieved_historical_excerpts>"

        # 2. Schema definition
        schema_json = json.dumps(ForecastResult.model_json_schema(), ensure_ascii=False, indent=2)

        prompt_blocks = [
            "=== SECTION 1: WORK METADATA & BOUNDARY ===",
            f"Work Version ID: {scope.target_work_version_id}",
            f"Cutoff Chapter: {cutoff_chapter}",
            f"Max Permitted Discourse Sequence: <= {scope.target_max_discourse_seq}",
            f"Manifest Hash: {scope.manifest_hash()}",
            "",
            "=== SECTION 2: PERMITTED SOURCE TEXTS ===",
            formatted_sources,
            "",
            "=== SECTION 3: CANON OVERLAYS & AUTHORIAL PRECEDENTS ===",
            f"Canon Divergences:\n{json.dumps(canon_context, ensure_ascii=False, indent=2)}",
            f"Author Decision Precedents:\n{json.dumps(author_precedents, ensure_ascii=False, indent=2)}",
            "",
            "=== SECTION 4: TASK & OUTPUT SCHEMA ===",
            f"Generate exactly {num_candidates} distinct prospective continuation hypotheses for Chapter {int(cutoff_chapter) + 1}.",
            "Each candidate must specify topology (POV, mode, pacing), 3-5 concrete sequential beats, character motivations, potential twist, and citations referencing provided source IDs.",
            "",
            "REQUIRED JSON SCHEMA:",
            schema_json,
            "",
            "Return ONLY a single valid JSON object adhering to this schema."
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
            raise ProviderUnavailableError(
                "Gemini provider requested, but GEMINI_API_KEY is not configured or google-genai is not installed. "
                "Configure GEMINI_API_KEY in settings.yaml or environment variables, or use provider='demo'."
            )

        system_instruction, prompt = self.build_forecast_prompt(
            scope=scope,
            target_context=target_context,
            author_precedents=author_precedents,
            canon_context=canon_context,
            num_candidates=num_candidates
        )

        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": ForecastResult,
                        "system_instruction": system_instruction
                    }
                )

                # Local validation against Pydantic schema
                result = ForecastResult.model_validate_json(response.text)
                result.provider = self.model_name
                result.is_synthetic_demonstration = False
                result.scope_manifest_hash = scope.manifest_hash()

                # Record metadata from context builder
                if "included_sources" in target_context:
                    result.included_sources = target_context["included_sources"]
                if "truncation_info" in target_context:
                    result.context_truncation_info = target_context["truncation_info"]

                # Extract usage metadata if provided
                usage = {}
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    um = response.usage_metadata
                    usage = {
                        "prompt_token_count": getattr(um, "prompt_token_count", None),
                        "candidates_token_count": getattr(um, "candidates_token_count", None),
                        "total_token_count": getattr(um, "total_token_count", None),
                    }
                result.raw_usage = usage

                return result

            except Exception as e:
                last_err = e
                logger.warning(f"Gemini generation attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(f"Gemini generation failed after {self.max_retries} attempts: {last_err}")
