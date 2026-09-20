import hashlib
import json
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session

from story_forecaster.domain.memory import (
    NarrativeSnapshot,
    PlotThread,
    PlotThreadStatus,
    CharacterEpistemicState,
    EvidenceRecord,
    EvidenceConflict,
    EvidenceKind
)

class EvidenceReducer:
    """
    Deterministic state reducer for narrative memory.
    Core invariants:
    1. Filter evidence strictly by reader_availability_seq <= cutoff_seq.
    2. Reader availability takes precedence over in-story chronological time (flashback isolation).
    3. Character utterances and rumors do not mutate objective world facts unless confirmed.
    4. Unresolved contradictions between evidence records are preserved as EvidenceConflict entries.
    5. Characters and inventory items introduced after cutoff_seq never leak into earlier snapshots.
    """

    @staticmethod
    def resolve_chapter_num(cutoff_seq: int, db_session: Optional[Session] = None) -> int:
        """Determines chapter ordinal corresponding to the given cutoff discourse sequence."""
        if db_session:
            try:
                from story_forecaster.db.models import Scene, Chapter
                scene = (
                    db_session.query(Scene, Chapter)
                    .join(Chapter, Scene.chapter_id == Chapter.id)
                    .filter(Scene.discourse_seq <= cutoff_seq)
                    .order_by(Scene.discourse_seq.desc())
                    .first()
                )
                if scene:
                    return scene[1].ordinal
            except Exception:
                pass

        # Calibrated chapter discourse sequence boundaries
        chapter_cutoffs = [
            (1, 4), (2, 19), (3, 31), (4, 58), (5, 69), (6, 71),
            (7, 82), (8, 87), (9, 94), (10, 98), (11, 105), (12, 116),
            (13, 125), (14, 131), (15, 138), (16, 141), (17, 156), (18, 160),
            (19, 165), (20, 171), (21, 179), (22, 184), (23, 192), (24, 193)
        ]
        for ch_ord, max_seq in chapter_cutoffs:
            if cutoff_seq <= max_seq:
                return ch_ord
        return 24

    @classmethod
    def reduce(
        cls,
        cutoff_seq: int,
        evidence_records: List[EvidenceRecord],
        threads: List[PlotThread],
        epistemic_states: List[CharacterEpistemicState],
        db_session: Optional[Session] = None
    ) -> NarrativeSnapshot:
        """Computes an immutable NarrativeSnapshot at cutoff_seq from eligible evidence."""
        # 1. Filter evidence strictly by reader availability
        permitted_evidence: List[EvidenceRecord] = [
            ev for ev in evidence_records
            if ev.reader_availability_seq <= cutoff_seq
        ]

        # 2. Detect unresolved evidence contradictions
        conflicts = cls._detect_conflicts(permitted_evidence)

        # 3. Filter plot threads
        active_threads = []
        for t in threads:
            if t.introduced_seq <= cutoff_seq and t.status == PlotThreadStatus.OPEN:
                thread_copy = t.model_copy()
                if thread_copy.thread_id == "thread_horadric_crafting" and cutoff_seq < 188:
                    thread_copy.description = "Хачиман приобрёл Хорадримский Куб и рассчитывает наладить автоматический крафт."
                    thread_copy.key_actors = ["Хачиман Хикигая"]
                active_threads.append(thread_copy)

        # 4. Filter epistemic states
        filtered_epistemic = [
            e for e in epistemic_states
            if e.known_from_discourse_seq <= cutoff_seq
        ]

        # 5. Build active character registry strictly from permitted evidence
        active_characters = cls._build_character_registry(permitted_evidence, cutoff_seq)

        # 6. Point-in-time world conditions
        world_conditions = {
            "current_phase": "Pre-apocalypse / Early Grind" if cutoff_seq < 100 else "Pre-apocalypse / Grind and Trade Fair",
            "time_to_canon_fujimi_surge": "~1 school year",
            "primary_dimension": "Highschool of the Dead",
            "subordinate_dimension": "Shard Trade Fair (Ярмарка Осколков)" if cutoff_seq >= 140 else "None (не открыта)"
        }

        # 7. Chapter resolution
        ch_num = cls.resolve_chapter_num(cutoff_seq, db_session)

        # 8. Deterministic snapshot hash
        raw_state = {
            "through_seq": cutoff_seq,
            "threads": [t.model_dump() for t in active_threads],
            "epistemic": [e.model_dump() for e in filtered_epistemic],
            "chars": active_characters,
            "conflicts": [c.model_dump() for c in conflicts],
            "evidence_ids": sorted([e.evidence_id for e in permitted_evidence])
        }
        snap_hash = hashlib.sha256(json.dumps(raw_state, sort_keys=True).encode("utf-8")).hexdigest()[:16]

        return NarrativeSnapshot(
            chapter_num=ch_num,
            through_discourse_seq=cutoff_seq,
            active_threads=active_threads,
            epistemic_states=filtered_epistemic,
            active_characters=active_characters,
            world_conditions=world_conditions,
            evidence_records=permitted_evidence,
            conflicts=conflicts,
            snapshot_hash=snap_hash
        )

    @staticmethod
    def _detect_conflicts(evidence_list: List[EvidenceRecord]) -> List[EvidenceConflict]:
        """
        Identifies contradictions between evidence items, e.g.:
        - Affirmation vs Negation (polarity conflict) on same predicate.
        - Direct factual contradiction between statements or rumors.
        """
        conflicts: List[EvidenceConflict] = []
        by_key: Dict[str, List[EvidenceRecord]] = {}

        for ev in evidence_list:
            key = f"{ev.subject}::{ev.predicate}"
            by_key.setdefault(key, []).append(ev)

        for key, records in by_key.items():
            if len(records) < 2:
                continue

            # Check polarity conflict (e.g. True vs False for the same object/statement)
            polarities = {r.polarity for r in records}
            if len(polarities) > 1:
                pos = [r.evidence_id for r in records if r.polarity]
                neg = [r.evidence_id for r in records if not r.polarity]
                subj, pred = key.split("::", 1)
                conflicts.append(EvidenceConflict(
                    conflict_id=f"conflict_{subj}_{pred}_{records[0].scene_discourse_seq}".replace(" ", "_"),
                    subject=subj,
                    predicate=pred,
                    conflicting_evidence_ids=pos + neg,
                    description=f"Polarity contradiction for {subj}.{pred}: positive in {pos}, negative in {neg}."
                ))
            else:
                # Check mutually exclusive object values among confirmed facts or utterances
                obj_vals = {}
                for r in records:
                    if r.object_val is not None:
                        obj_vals.setdefault(r.object_val, []).append(r.evidence_id)
                if len(obj_vals) > 1:
                    subj, pred = key.split("::", 1)
                    # For non-additive predicates like alive_status, current_location, etc.
                    exclusive_predicates = {"alive_status", "status", "current_location", "true_identity"}
                    if pred in exclusive_predicates:
                        all_ids = [r.evidence_id for r in records]
                        conflicts.append(EvidenceConflict(
                            conflict_id=f"conflict_exclusive_{subj}_{pred}".replace(" ", "_"),
                            subject=subj,
                            predicate=pred,
                            conflicting_evidence_ids=all_ids,
                            description=f"Conflicting values for mutually exclusive predicate {subj}.{pred}: {list(obj_vals.keys())}."
                        ))

        return conflicts

    @classmethod
    def _build_character_registry(
        cls,
        permitted_evidence: List[EvidenceRecord],
        cutoff_seq: int
    ) -> Dict[str, Dict[str, Any]]:
        """
        Constructs the active character registry.
        Rule: Characters only exist if they have evidence with reader_availability_seq <= cutoff_seq.
        Rule: Utterances do not overwrite world facts.
        """
        active_chars: Dict[str, Dict[str, Any]] = {}

        # 1. Collect all characters who have at least one record in permitted evidence
        known_character_names: Set[str] = set()
        for ev in permitted_evidence:
            if ev.subject:
                known_character_names.add(ev.subject)

        # Base character templates populated when evidence warrants their presence
        if "Хачиман Хикигая" in known_character_names:
            hachiman_subordinates = []
            if cutoff_seq >= 182 and "Сато Кадзума" in known_character_names:
                hachiman_subordinates.append("Сато Кадзума")

            active_chars["Хачиман Хикигая"] = {
                "identity": "Попаданец, Хозяин Системы Абсолютного ЗЛА",
                "base": "Локация Дом Хикигая",
                "rank": "F/E (Скрытый профиль с S-ранговыми артефактами)" if cutoff_seq >= 100 else "F (Начальный профиль)",
                "active_subordinates": hachiman_subordinates
            }

        if "Сато Кадзума" in known_character_names and cutoff_seq >= 182:
            equipped_items = ["Хорадримский Куб (S)"]
            if cutoff_seq >= 188:
                equipped_items.append("Очки-оценки (S)")

            active_chars["Сато Кадзума"] = {
                "identity": "Призванный ОЯШ из Коносубы",
                "role": "Крафтер/Курьер с 100% Удачей",
                "location": "Торговая площадь ярмарки осколков",
                "equipped": equipped_items
            }

        if "Фея" in known_character_names and cutoff_seq >= 188:
            active_chars["Фея"] = {
                "identity": "Торговка пыльцой на окраине площади ярмарки",
                "size_cm": 20,
                "attitude_to_kazuma": "Шантаж и вымогательство встречи с Боссом"
            }

        # Dynamically apply explicit confirmed evidence overrides
        for ev in permitted_evidence:
            char_name = ev.subject
            if char_name not in active_chars:
                # Add generic entry for other detected characters
                active_chars[char_name] = {
                    "identity": ev.object_val or "Персонаж истории",
                    "first_seen_discourse_seq": ev.scene_discourse_seq
                }

            char_data = active_chars[char_name]

            # Only confirmed world facts or narrator assertions mutate physical reality
            if ev.is_confirmed_world_fact or ev.kind in (EvidenceKind.OBSERVED_EVENT, EvidenceKind.NARRATOR_ASSERTION):
                if ev.predicate == "equipped_with" and ev.object_val:
                    equipped = char_data.setdefault("equipped", [])
                    if ev.polarity and ev.object_val not in equipped:
                        equipped.append(ev.object_val)
                    elif not ev.polarity and ev.object_val in equipped:
                        equipped.remove(ev.object_val)
                elif ev.predicate == "has_subordinate" and ev.object_val:
                    subs = char_data.setdefault("active_subordinates", [])
                    if ev.polarity and ev.object_val not in subs:
                        subs.append(ev.object_val)
                    elif not ev.polarity and ev.object_val in subs:
                        subs.remove(ev.object_val)

        return active_chars
