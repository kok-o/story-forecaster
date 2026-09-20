import os
import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from .base import BaseLLMProvider, ProviderUnavailableError
from ..domain.scope import ForecastScope
from ..domain.forecast import ForecastResult, PredictionCandidate
from ..domain.canon import ReferenceClassification
from ..domain.writing import ScenePlan, CharacterVoiceProfile, SceneSynthesisOutput
from ..domain.memory import NarrativeSnapshot

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

        # 3. Narrative memory & character epistemic matrix
        epistemic_raw = target_context.get("epistemic_states", [])
        characters_raw = target_context.get("characters", {})
        world_raw = target_context.get("world_conditions", {})
        threads_raw = target_context.get("active_threads", [])

        memory_blocks = []
        if characters_raw:
            memory_blocks.append(f"Active Characters:\n{json.dumps(characters_raw, ensure_ascii=False, indent=2)}")
        if epistemic_raw:
            memory_blocks.append(f"Character Epistemic States (Knowledge Boundaries):\n{json.dumps(epistemic_raw, ensure_ascii=False, indent=2)}")
        if world_raw:
            memory_blocks.append(f"World Conditions:\n{json.dumps(world_raw, ensure_ascii=False, indent=2)}")
        if threads_raw:
            memory_blocks.append(f"Open Plot Threads:\n{json.dumps(threads_raw, ensure_ascii=False, indent=2)}")

        memory_section = "\n\n".join(memory_blocks) if memory_blocks else "None established."

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
            "=== SECTION 2.5: NARRATIVE MEMORY & CHARACTER EPISTEMIC LIMITS ===",
            memory_section,
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

    def build_scene_synthesis_prompt(
        self,
        plan: ScenePlan,
        snapshot: NarrativeSnapshot,
        voice_profiles: List[CharacterVoiceProfile],
        recent_scenes: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, str]:
        system_instruction = (
            "You are an expert Russian light-novel author writing an ongoing novel continuation scene in the distinctive style of author N.B.\n\n"
            "CRITICAL NARRATIVE AND EPISTEMIC CONSTRAINTS:\n"
            f"1. POINT OF VIEW INTEGRITY: The scene must be narrated strictly from the perspective of POV character '{plan.pov_character}'. "
            "Internal monologues, sensory impressions, and emotional filters belong exclusively to this POV character. "
            "Never leak omniscient insights or narrate the internal, hidden thoughts of interlocutors.\n"
            "2. EPISTEMIC INTEGRITY (THEORY OF MIND): Characters cannot speak of, react to, or act upon facts they do not possess. "
            "Respect the exact knowledge state of each participant.\n"
            "3. CHARACTER VOICES: Every dialogue line and interpersonal exchange must strictly follow the character's voice profile, "
            "vocabulary tone, sentence structure, and mannerisms.\n"
            "4. CITATION INTEGRITY FOR DELTAS: In all extracted inventory_changes, injuries_or_statuses, epistemic_updates, and dialogue_claims, "
            "the 'span_quote' field MUST be an EXACT, VERBATIM substring copied directly from your generated prose. Never paraphrase or alter punctuation in quotes.\n"
            "5. DIALOGUE CLAIMS: When a character boasts, threatens, lies, or makes unverified statements in dialogue, "
            "record it in 'dialogue_claims' with is_world_fact=false.\n"
            "6. BEAT COMPLIANCE: Execute all mandatory plot beats in chronological sequence while respecting target pacing and outcome."
        )

        prompt_blocks = [
            f"# SCENE BLUEPRINT: {plan.scene_goal}",
            f"POV Character: {plan.pov_character}",
            f"Participants: {', '.join(plan.participants)}",
            f"Initial State: {plan.initial_state_summary}",
            f"Conflict Type: {plan.conflict_kind}",
            f"Desired Outcome: {plan.desired_outcome}",
            f"Target Pacing: {plan.target_pacing}",
            f"Target Length: ~{plan.target_length_chars} characters",
            "",
            "## MANDATORY PLOT BEATS (Must occur in sequence):",
        ]
        for i, beat in enumerate(plan.mandatory_beats, 1):
            prompt_blocks.append(f"{i}. {beat}")

        if plan.permitted_changes:
            prompt_blocks.append("\n## PERMITTED STATE CHANGES:")
            for ch in plan.permitted_changes:
                prompt_blocks.append(f"- {ch}")

        if plan.known_information:
            prompt_blocks.append("\n## THEORY OF MIND / KNOWN INFORMATION AT SCENE START:")
            for char, facts in plan.known_information.items():
                prompt_blocks.append(f"- {char}: {', '.join(facts)}")

        if voice_profiles:
            prompt_blocks.append("\n## CHARACTER VOICE PROFILES:")
            for vp in voice_profiles:
                mannerisms = "; ".join(vp.dialogue_mannerisms) if vp.dialogue_mannerisms else "None specified"
                prompt_blocks.append(
                    f"### Character: {vp.character_id}\n"
                    f"- Tone: {vp.vocabulary_tone}\n"
                    f"- Sentence Length: {vp.typical_sentence_length}\n"
                    f"- Mannerisms: {mannerisms}\n"
                    f"- Rationale: {vp.author_tuning_rationale}"
                )

        if snapshot:
            prompt_blocks.append("\n## CURRENT NARRATIVE SNAPSHOT:")
            if getattr(snapshot, "active_characters", None):
                prompt_blocks.append("Active Characters & Items/Statuses:")
                for char, data in snapshot.active_characters.items():
                    inv = data.get("inventory", [])
                    st = data.get("statuses", [])
                    prompt_blocks.append(f"  * {char}: inventory=[{', '.join(inv)}], statuses=[{', '.join(st)}]")
            if getattr(snapshot, "epistemic_states", None):
                prompt_blocks.append("Character Epistemic Matrix (Beliefs & Known Facts):")
                for ep in snapshot.epistemic_states[:10]:
                    att_val = ep.attitude.value if hasattr(ep.attitude, "value") else str(ep.attitude)
                    prompt_blocks.append(f"  * {ep.character_id} knows '{ep.fact_key}' (Attitude: {att_val})")

        if recent_scenes:
            prompt_blocks.append("\n## PRECEDING SCENE CONTEXT:")
            for sc in recent_scenes[-2:]:
                prompt_blocks.append(f"- Scene {sc.get('scene_ordinal', '?')} ({sc.get('title', 'Untitled')}): {sc.get('content', '')[:300]}...")

        prompt_blocks.extend([
            "",
            "Generate the complete Russian literary narrative prose for this scene adhering to all constraints.",
            "Simultaneously extract all state deltas (inventory changes, injuries/statuses, epistemic updates, dialogue claims, introduced characters) "
            "with EXACT, VERBATIM span_quote citations copied directly from your prose."
        ])

        return system_instruction, "\n".join(prompt_blocks)

    def synthesize_scene_prose(
        self,
        plan: ScenePlan,
        snapshot: NarrativeSnapshot,
        voice_profiles: List[CharacterVoiceProfile],
        recent_scenes: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        if not self.is_available():
            raise ProviderUnavailableError(
                "Gemini provider requested, but GEMINI_API_KEY is not configured or google-genai is not installed. "
                "Configure GEMINI_API_KEY in settings.yaml or environment variables, or use provider='demo'."
            )

        system_instruction, prompt = self.build_scene_synthesis_prompt(
            plan=plan,
            snapshot=snapshot,
            voice_profiles=voice_profiles,
            recent_scenes=recent_scenes
        )

        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": SceneSynthesisOutput,
                        "system_instruction": system_instruction
                    }
                )

                output = SceneSynthesisOutput.model_validate_json(response.text)
                delta_dict = {
                    "introduced_characters": output.introduced_characters,
                    "inventory_changes": output.inventory_changes,
                    "injuries_or_statuses": output.injuries_or_statuses,
                    "epistemic_updates": output.epistemic_updates,
                    "dialogue_claims": output.dialogue_claims,
                    "is_synthetic_demonstration": False,
                    "provider": self.model_name
                }
                return output.prose, delta_dict

            except Exception as e:
                last_err = e
                logger.warning(f"Gemini scene synthesis attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(f"Gemini scene synthesis failed after {self.max_retries} attempts: {last_err}")
