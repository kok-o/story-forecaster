import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from story_forecaster.db.models import Branch, BranchScene, WorkVersion
from story_forecaster.domain.writing import (
    ScenePlan, ProposedStateDelta, SceneValidationResult, CharacterVoiceProfile
)
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.memory import (
    NarrativeSnapshot, EpistemicAttitude, CharacterEpistemicState
)
from story_forecaster.memory.engine import NarrativeMemoryEngine
from story_forecaster.writing.voice import VoiceRegistry
from story_forecaster.writing.validator import SceneValidator
from story_forecaster.writing.synthesizer import SceneSynthesizer
from story_forecaster.providers.base import BaseLLMProvider


class BranchService:
    """
    Manages isolated fanfic divergence branches, scene lifecycles, and narrative state evolution:
    1. Zero-leakage branch isolation: original book canonical entities are never mutated.
    2. Atomic scene state machine: DRAFT -> ACCEPTED, REJECTED, or SUPERSEDED.
    3. Reversible state updates: rejected scenes never alter branch memory.
    4. Canceled injuries are eliminated from subsequent snapshots.
    5. Clean Markdown/TXT export of validated fanfic branches.
    """

    def __init__(
        self,
        voice_registry: Optional[VoiceRegistry] = None,
        validator: Optional[SceneValidator] = None,
        synthesizer: Optional[SceneSynthesizer] = None
    ):
        self.voice_registry = voice_registry or VoiceRegistry()
        self.validator = validator or SceneValidator()
        self.synthesizer = synthesizer or SceneSynthesizer()

    def create_branch(
        self,
        session: Session,
        project_id: str,
        parent_work_version_id: str,
        cutoff_discourse_seq: int,
        branch_name: str,
        description: Optional[str] = None
    ) -> Branch:
        """
        Creates an isolated fanfic branch branching off from an exact version and sequence cutoff.
        Guarantees that canonical chapters and scenes remain untouched.
        """
        branch = Branch(
            project_id=project_id,
            parent_work_version_id=parent_work_version_id,
            cutoff_discourse_seq=cutoff_discourse_seq,
            branch_name=branch_name,
            description=description or f"Alternative branch off version {parent_work_version_id} at sequence {cutoff_discourse_seq}",
            status="ACTIVE"
        )
        session.add(branch)
        session.commit()
        session.refresh(branch)
        return branch

    def draft_scene(
        self,
        session: Session,
        branch_id: str,
        scene_ordinal: int,
        title: str,
        plan: ScenePlan,
        provider: Optional[BaseLLMProvider] = None
    ) -> Tuple[BranchScene, SceneValidationResult, ProposedStateDelta]:
        """
        Drafts a fanfic scene from a structured plan.
        Synthesizes prose, validates constraints against prior branch state,
        and saves as DRAFT status with an unapplied ProposedStateDelta.
        """
        branch = session.query(Branch).filter(Branch.id == branch_id).one_or_none()
        if not branch:
            raise ValueError(f"Branch '{branch_id}' not found.")

        # Compute branch snapshot through prior scene
        snapshot = self.get_branch_snapshot(session, branch_id, through_scene_ordinal=scene_ordinal - 1)

        # Collect character voice profiles for participants
        voice_profiles = [
            self.voice_registry.get_profile(c)
            for c in plan.participants
            if self.voice_registry.get_profile(c) is not None
        ]

        # Synthesize prose and extract proposed state delta
        prose, delta = self.synthesizer.synthesize(
            branch_id=branch_id,
            scene_ordinal=scene_ordinal,
            plan=plan,
            snapshot=snapshot,
            voice_profiles=voice_profiles,
            provider=provider
        )

        # Validate against constraints
        validation = self.validator.validate_scene(plan=plan, content=prose, snapshot=snapshot)

        # Check existing revision count for this ordinal
        existing_scenes = (
            session.query(BranchScene)
            .filter(BranchScene.branch_id == branch_id, BranchScene.scene_ordinal == scene_ordinal)
            .all()
        )
        revision_num = max([s.revision_num for s in existing_scenes], default=0) + 1

        branch_scene = BranchScene(
            branch_id=branch_id,
            scene_ordinal=scene_ordinal,
            revision_num=revision_num,
            title=title,
            scene_plan_json=plan.model_dump(),
            content=prose,
            status="DRAFT",
            state_delta_json=delta.model_dump()
        )
        session.add(branch_scene)
        session.commit()
        session.refresh(branch_scene)

        return branch_scene, validation, delta

    def accept_scene(self, session: Session, scene_id: str) -> BranchScene:
        """
        Formally accepts a drafted scene, transitioning it to ACCEPTED.
        Only accepted scenes mutate the branch's downstream narrative snapshot.
        """
        scene = session.query(BranchScene).filter(BranchScene.id == scene_id).one_or_none()
        if not scene:
            raise ValueError(f"BranchScene '{scene_id}' not found.")

        scene.status = "ACCEPTED"
        if scene.state_delta_json:
            delta_dict = dict(scene.state_delta_json)
            delta_dict["validation_status"] = "ACCEPTED"
            scene.state_delta_json = delta_dict

        session.commit()
        session.refresh(scene)
        return scene

    def reject_scene(self, session: Session, scene_id: str, reason: str = "") -> BranchScene:
        """
        Rejects a drafted scene.
        Its state delta is completely quarantined and will NEVER alter branch memory.
        """
        scene = session.query(BranchScene).filter(BranchScene.id == scene_id).one_or_none()
        if not scene:
            raise ValueError(f"BranchScene '{scene_id}' not found.")

        scene.status = "REJECTED"
        if scene.state_delta_json:
            delta_dict = dict(scene.state_delta_json)
            delta_dict["validation_status"] = "REJECTED"
            delta_dict["validation_notes"] = reason
            scene.state_delta_json = delta_dict

        session.commit()
        session.refresh(scene)
        return scene

    def revise_scene(
        self,
        session: Session,
        scene_id: str,
        new_content: str,
        new_plan: Optional[ScenePlan] = None,
        provider: Optional[BaseLLMProvider] = None
    ) -> Tuple[BranchScene, SceneValidationResult, ProposedStateDelta]:
        """
        Replaces a scene with a new revision:
        - Marks old scene revision as SUPERSEDED.
        - Creates new BranchScene with incremented revision_num.
        - Recomputes delta and runs validation.
        """
        old_scene = session.query(BranchScene).filter(BranchScene.id == scene_id).one_or_none()
        if not old_scene:
            raise ValueError(f"BranchScene '{scene_id}' not found.")

        old_scene.status = "SUPERSEDED"

        plan = new_plan or ScenePlan.model_validate(old_scene.scene_plan_json)
        snapshot = self.get_branch_snapshot(session, old_scene.branch_id, through_scene_ordinal=old_scene.scene_ordinal - 1)

        delta = self.synthesizer._extract_state_delta(
            branch_id=old_scene.branch_id,
            scene_ordinal=old_scene.scene_ordinal,
            content=new_content,
            plan=plan
        )
        validation = self.validator.validate_scene(plan=plan, content=new_content, snapshot=snapshot)

        new_scene = BranchScene(
            branch_id=old_scene.branch_id,
            scene_ordinal=old_scene.scene_ordinal,
            revision_num=old_scene.revision_num + 1,
            title=old_scene.title,
            scene_plan_json=plan.model_dump(),
            content=new_content,
            status="ACCEPTED" if validation.passed else "DRAFT",
            state_delta_json=delta.model_dump()
        )
        session.add(new_scene)
        session.commit()
        session.refresh(new_scene)

        return new_scene, validation, delta

    def rollback_injury(
        self,
        session: Session,
        branch_id: str,
        character_id: str,
        injury_status: str,
        scene_ordinal: Optional[int] = None
    ) -> BranchScene:
        """
        Records a state transition delta canceling or healing an injury/status.
        Ensures subsequent snapshots exclude the status from character memory.
        """
        branch = session.query(Branch).filter(Branch.id == branch_id).one_or_none()
        if not branch:
            raise ValueError(f"Branch '{branch_id}' not found.")

        # Determine target ordinal: if not specified, find max ordinal and increment
        if scene_ordinal is None:
            max_ord = (
                session.query(BranchScene.scene_ordinal)
                .filter(BranchScene.branch_id == branch_id)
                .order_by(BranchScene.scene_ordinal.desc())
                .first()
            )
            scene_ordinal = (max_ord[0] + 1) if max_ord else 1

        delta = ProposedStateDelta(
            delta_id=f"delta_healing_{branch_id[:6]}_{scene_ordinal}",
            branch_id=branch_id,
            scene_ordinal=scene_ordinal,
            injuries_or_statuses=[{
                "character": character_id,
                "status": injury_status,
                "action": "canceled",
                "span_quote": f"Статус '{injury_status}' персонажа {character_id} был нейтрализован/исцелен."
            }],
            validation_status="ACCEPTED"
        )

        plan = ScenePlan(
            scene_goal=f"Нейтрализация и снятие статуса {injury_status}",
            pov_character=character_id,
            participants=[character_id],
            initial_state_summary=f"{character_id} освобождается от эффекта {injury_status}.",
            mandatory_beats=[f"Снятие эффекта {injury_status}"],
            desired_outcome=f"Статус {injury_status} полностью аннулирован."
        )

        healing_scene = BranchScene(
            branch_id=branch_id,
            scene_ordinal=scene_ordinal,
            revision_num=1,
            title=f"Исцеление: {injury_status}",
            scene_plan_json=plan.model_dump(),
            content=f"Действие статуса '{injury_status}' на персонажа {character_id} прекратилось. Дыхание восстановилось, разум очистился.",
            status="ACCEPTED",
            state_delta_json=delta.model_dump()
        )
        session.add(healing_scene)
        session.commit()
        session.refresh(healing_scene)
        return healing_scene

    def get_branch_snapshot(
        self,
        session: Session,
        branch_id: str,
        through_scene_ordinal: Optional[int] = None
    ) -> NarrativeSnapshot:
        """
        Builds the narrative snapshot for the branch at a given scene cutoff.
        Replays accepted deltas sequentially onto the baseline canon cutoff snapshot:
        - Rejected and draft scenes do NOT alter memory.
        - Dialogue boasts (is_world_fact=False) do NOT mutate physical world facts.
        - Canceled injuries are eliminated from downstream snapshots.
        """
        branch = session.query(Branch).filter(Branch.id == branch_id).one_or_none()
        if not branch:
            raise ValueError(f"Branch '{branch_id}' not found.")

        # 1. Build immutable baseline snapshot at branch bifurcation cutoff
        memory_engine = NarrativeMemoryEngine(db_session=session)
        scope = ForecastScope(
            project_id=branch.project_id,
            target_work_version_id=branch.parent_work_version_id,
            target_max_discourse_seq=branch.cutoff_discourse_seq
        )
        baseline = memory_engine.get_snapshot(scope)

        # Deep copy snapshot structures to allow isolated replay
        active_chars = {k: json.loads(json.dumps(v)) for k, v in baseline.active_characters.items()}
        epistemic_list = [e.model_copy() for e in baseline.epistemic_states]
        active_threads = [t.model_copy() for t in baseline.active_threads]
        world_conds = dict(baseline.world_conditions)

        # 2. Query all ACCEPTED branch scenes up to through_scene_ordinal
        query = session.query(BranchScene).filter(
            BranchScene.branch_id == branch_id,
            BranchScene.status == "ACCEPTED"
        )
        if through_scene_ordinal is not None:
            query = query.filter(BranchScene.scene_ordinal <= through_scene_ordinal)

        scenes = query.order_by(BranchScene.scene_ordinal.asc(), BranchScene.revision_num.desc()).all()

        # Deduplicate to pick latest revision per scene_ordinal
        latest_scenes_by_ord: Dict[int, BranchScene] = {}
        for s in scenes:
            if s.scene_ordinal not in latest_scenes_by_ord:
                latest_scenes_by_ord[s.scene_ordinal] = s

        sorted_scenes = [latest_scenes_by_ord[k] for k in sorted(latest_scenes_by_ord.keys())]

        # 3. Replay accepted deltas sequentially
        for sc in sorted_scenes:
            delta_json = sc.state_delta_json or {}

            # Introduced characters
            for char_name in delta_json.get("introduced_characters", []):
                if char_name not in active_chars:
                    active_chars[char_name] = {
                        "identity": f"Появился в фанфик-сцене {sc.scene_ordinal}",
                        "equipped": [],
                        "statuses": []
                    }

            # Inventory changes
            for inv in delta_json.get("inventory_changes", []):
                char = inv.get("character")
                item = inv.get("item")
                action = inv.get("action")
                if char and item:
                    char_entry = active_chars.setdefault(char, {"identity": "Персонаж истории", "equipped": [], "statuses": []})
                    eq_list = char_entry.setdefault("equipped", [])
                    if action in ("equipped", "acquired"):
                        if item not in eq_list:
                            eq_list.append(item)
                    elif action in ("lost", "removed"):
                        if item in eq_list:
                            eq_list.remove(item)

            # Injuries / statuses (including cancellation/healing)
            for inj in delta_json.get("injuries_or_statuses", []):
                char = inj.get("character")
                st = inj.get("status")
                action = inj.get("action")
                if char and st:
                    char_entry = active_chars.setdefault(char, {"identity": "Персонаж истории", "equipped": [], "statuses": []})
                    st_list = char_entry.setdefault("statuses", [])
                    if action in ("applied", "inflicted"):
                        if st not in st_list:
                            st_list.append(st)
                    elif action in ("healed", "canceled", "removed"):
                        if st in st_list:
                            st_list.remove(st)

            # Epistemic state updates
            for ep in delta_json.get("epistemic_updates", []):
                char = ep.get("character")
                fkey = ep.get("fact_key")
                att_str = ep.get("attitude", "KNOWN")
                att = EpistemicAttitude[att_str] if att_str in EpistemicAttitude.__members__ else EpistemicAttitude.KNOWN
                # Update existing or append
                found = False
                for existing in epistemic_list:
                    if existing.character_id == char and existing.fact_key == fkey:
                        existing.attitude = att
                        found = True
                        break
                if not found and char and fkey:
                    epistemic_list.append(
                        CharacterEpistemicState(
                            character_id=char,
                            fact_key=fkey,
                            attitude=att,
                            known_from_discourse_seq=branch.cutoff_discourse_seq + sc.scene_ordinal
                        )
                    )

            # Dialogue claims: Note that dialogue boast/threat (is_world_fact=False)
            # is explicitly NOT converted into physical world conditions or character attributes!

        # 4. Deterministic snapshot fingerprint
        raw_state = {
            "branch_id": branch_id,
            "cutoff_seq": branch.cutoff_discourse_seq,
            "through_scene": through_scene_ordinal,
            "chars": active_chars,
            "epistemic": [e.model_dump() for e in epistemic_list]
        }
        snap_hash = hashlib.sha256(json.dumps(raw_state, sort_keys=True).encode("utf-8")).hexdigest()[:16]

        max_scene_ord = sorted_scenes[-1].scene_ordinal if sorted_scenes else 0

        return NarrativeSnapshot(
            chapter_num=baseline.chapter_num,
            through_discourse_seq=branch.cutoff_discourse_seq + max_scene_ord,
            active_threads=active_threads,
            epistemic_states=epistemic_list,
            active_characters=active_chars,
            world_conditions=world_conds,
            evidence_records=baseline.evidence_records,
            conflicts=baseline.conflicts,
            snapshot_hash=snap_hash
        )

    def export_branch(self, session: Session, branch_id: str, format: str = "markdown") -> str:
        """
        Exports all accepted scenes of the branch in sequential order to Markdown or Plain Text.
        """
        branch = session.query(Branch).filter(Branch.id == branch_id).one_or_none()
        if not branch:
            raise ValueError(f"Branch '{branch_id}' not found.")

        query = session.query(BranchScene).filter(
            BranchScene.branch_id == branch_id,
            BranchScene.status == "ACCEPTED"
        ).order_by(BranchScene.scene_ordinal.asc(), BranchScene.revision_num.desc())

        scenes = query.all()
        # Take latest revision per ordinal
        latest_by_ord: Dict[int, BranchScene] = {}
        for s in scenes:
            if s.scene_ordinal not in latest_by_ord:
                latest_by_ord[s.scene_ordinal] = s

        ordered_scenes = [latest_by_ord[k] for k in sorted(latest_by_ord.keys())]

        if format.lower() == "markdown":
            lines = [
                f"# {branch.branch_name}",
                f"",
                f"**Родительская версия:** `{branch.parent_work_version_id}`  ",
                f"**Точка бифуркации:** Sequence {branch.cutoff_discourse_seq}  ",
                f"**Описание:** {branch.description or 'Альтернативная сюжетная линия'}",
                f"",
                f"---",
                f""
            ]
            for s in ordered_scenes:
                plan_dict = s.scene_plan_json or {}
                pov = plan_dict.get("pov_character", "Unknown")
                participants = ", ".join(plan_dict.get("participants", []))
                lines.append(f"## Сцена {s.scene_ordinal}: {s.title}")
                lines.append(f"**POV:** {pov} | **Участники:** {participants}\n")
                lines.append(s.content)
                lines.append("\n---\n")
            return "\n".join(lines)
        else:
            # Plain Text
            lines = [
                f"=== ВЕТКА: {branch.branch_name} ===",
                f"Родительская версия: {branch.parent_work_version_id}",
                f"Точка бифуркации: Sequence {branch.cutoff_discourse_seq}",
                f"Описание: {branch.description or 'Альтернативная сюжетная линия'}",
                f"=" * 50,
                ""
            ]
            for s in ordered_scenes:
                plan_dict = s.scene_plan_json or {}
                pov = plan_dict.get("pov_character", "Unknown")
                lines.append(f"--- СЦЕНА {s.scene_ordinal}: {s.title} (POV: {pov}) ---")
                lines.append(s.content)
                lines.append("")
            return "\n".join(lines)
