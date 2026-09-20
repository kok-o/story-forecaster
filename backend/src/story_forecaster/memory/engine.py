import hashlib
import json
from typing import List, Dict, Any, Optional
from ..domain.scope import ForecastScope
from ..domain.memory import (
    NarrativeSnapshot,
    PlotThread,
    PlotThreadKind,
    PlotThreadStatus,
    CharacterEpistemicState,
    EpistemicAttitude,
    EpistemicKind
)

class NarrativeMemoryEngine:
    """
    Manages structured narrative state, plot threads, and Theory of Mind matrices
    under strict ForecastScope boundary constraints.
    """

    def __init__(self, db_session: Optional[Any] = None):
        self._db_session = db_session
        self._threads: List[PlotThread] = []
        self._epistemic_states: List[CharacterEpistemicState] = []
        self._initialize_baseline_canon_and_threads()

    def _initialize_baseline_canon_and_threads(self):
        """Pre-populates verified plot hooks and state established up to chapter 23."""
        # 1. Active Plot Threads (Чеховские ружья)
        self._threads = [
            PlotThread(
                thread_id="thread_kazuma_fairy_dust",
                title="Шантаж феи и покупка пыльцы фей",
                kind=PlotThreadKind.ACQUISITION_GOAL,
                status=PlotThreadStatus.OPEN,
                introduced_chapter=23,
                introduced_seq=188,
                last_active_chapter=23,
                urgency=5,
                key_actors=["Сато Кадзума", "Фея", "Хачиман Хикигая"],
                description="Фея требует отвести ее к Боссу под угрозой ославить 'шест' Кадзумы перед всей ярмаркой. Кадзума в панике выбирает между позором и гневом Хачимана."
            ),
            PlotThread(
                thread_id="thread_horadric_crafting",
                title="Наладка производства через Хорадримский Куб",
                kind=PlotThreadKind.ACQUISITION_GOAL,
                status=PlotThreadStatus.OPEN,
                introduced_chapter=22,
                introduced_seq=182,
                last_active_chapter=23,
                urgency=4,
                key_actors=["Хачиман Хикигая", "Сато Кадзума"],
                description="Хачиман купил Кадзуму за 400 000 золотых из-за 100% удачи и вручил ему S-ранговый Хорадримский Куб для синтеза артефактов."
            ),
            PlotThread(
                thread_id="thread_dungeon_surge_prevention",
                title="Подготовка к Выбросу зомби в Академии Фудзими",
                kind=PlotThreadKind.TICKING_CLOCK,
                status=PlotThreadStatus.OPEN,
                introduced_chapter=12,
                introduced_seq=106,
                last_active_chapter=21,
                urgency=4,
                key_actors=["Хачиман Хикигая", "Комачи Хикигая"],
                description="До канонического апокалипсиса/выброса из данжа Фудзими остается около года; Хачиман форсирует прокачку и сбор ресурсов."
            ),
            PlotThread(
                thread_id="thread_fujimi_canon_cast",
                title="Академия Фудзими и канонические герои HOTD",
                kind=PlotThreadKind.MYSTERY,
                status=PlotThreadStatus.OPEN,
                introduced_chapter=12,
                introduced_seq=110,
                last_active_chapter=20,
                urgency=3,
                key_actors=["Такаши Комуро", "Саэко Бусуджима", "Рэй Миямото", "Сая Такаги"],
                description="Канонические ученики Фудзими живут обычной школьной жизнью, не подозревая о существовании данжа и готовящемся выбросе."
            )
        ]

        # 2. Epistemic Matrix (Theory of Mind)
        self._epistemic_states = [
            CharacterEpistemicState(
                character_id="Хачиман Хикигая",
                fact_key="apocalypse_is_dungeon_surge",
                attitude=EpistemicAttitude.KNOWN,
                known_from_discourse_seq=140
            ),
            CharacterEpistemicState(
                character_id="Хачиман Хикигая",
                fact_key="kazuma_luck_bonus",
                attitude=EpistemicAttitude.KNOWN,
                known_from_discourse_seq=182
            ),
            CharacterEpistemicState(
                character_id="Сато Кадзума",
                fact_key="boss_has_evil_system_and_ogres",
                attitude=EpistemicAttitude.KNOWN,
                known_from_discourse_seq=185
            ),
            CharacterEpistemicState(
                character_id="Сато Кадзума",
                fact_key="fairy_blackmail_threat",
                attitude=EpistemicAttitude.KNOWN,
                known_from_discourse_seq=192
            ),
            CharacterEpistemicState(
                character_id="Хачиман Хикигая",
                fact_key="fairy_blackmail_threat",
                attitude=EpistemicAttitude.IGNORANT,  # Boss does not know yet!
                known_from_discourse_seq=192
            ),
            CharacterEpistemicState(
                character_id="Саэко Бусуджима",
                fact_key="hachiman_system_power",
                attitude=EpistemicAttitude.IGNORANT,
                known_from_discourse_seq=192
            )
        ]

    def get_snapshot(self, scope: ForecastScope) -> NarrativeSnapshot:
        """
        Builds a point-in-time narrative state snapshot filtered strictly
        by the maximum discourse sequence permitted by scope.
        """
        cutoff_seq = scope.target_max_discourse_seq

        # 1. Resolve chapter ordinal point-in-time
        ch_num = None
        if self._db_session:
            try:
                from story_forecaster.db.models import Scene, Chapter
                scene = (
                    self._db_session.query(Scene, Chapter)
                    .join(Chapter, Scene.chapter_id == Chapter.id)
                    .filter(Scene.discourse_seq <= cutoff_seq)
                    .order_by(Scene.discourse_seq.desc())
                    .first()
                )
                if scene:
                    ch_num = scene[1].ordinal
            except Exception:
                pass

        if ch_num is None:
            # Calibrated discourse sequence boundaries for the target work
            chapter_cutoffs = [
                (1, 4), (2, 19), (3, 31), (4, 58), (5, 69), (6, 71),
                (7, 82), (8, 87), (9, 94), (10, 98), (11, 105), (12, 116),
                (13, 125), (14, 131), (15, 138), (16, 141), (17, 156), (18, 160),
                (19, 165), (20, 171), (21, 179), (22, 184), (23, 192), (24, 193)
            ]
            for ch_ord, max_seq in chapter_cutoffs:
                if cutoff_seq <= max_seq:
                    ch_num = ch_ord
                    break
            if ch_num is None:
                ch_num = 24

        # 2. Filter threads and their descriptions point-in-time
        active_threads = []
        for t in self._threads:
            if t.introduced_seq <= cutoff_seq and t.status == PlotThreadStatus.OPEN:
                thread_copy = t.model_copy()
                if thread_copy.thread_id == "thread_horadric_crafting" and cutoff_seq < 188:
                    thread_copy.description = "Хачиман приобрёл Хорадримский Куб и рассчитывает наладить автоматический крафт."
                    thread_copy.key_actors = ["Хачиман Хикигая"]
                active_threads.append(thread_copy)

        # 3. Filter epistemic states known up to cutoff
        epistemic = [
            e for e in self._epistemic_states
            if e.known_from_discourse_seq <= cutoff_seq
        ]

        # 4. Point-in-time character registry (no future leaks!)
        active_chars: Dict[str, Any] = {}
        hachiman_subordinates = ["Сато Кадзума"] if cutoff_seq >= 182 else []
        active_chars["Хачиман Хикигая"] = {
            "identity": "Попаданец, Хозяин Системы Абсолютного ЗЛА",
            "base": "Локация Дом Хикигая",
            "rank": "F/E (Скрытый профиль с S-ранговыми артефактами)" if cutoff_seq >= 100 else "F (Начальный профиль)",
            "active_subordinates": hachiman_subordinates
        }

        if cutoff_seq >= 182:
            active_chars["Сато Кадзума"] = {
                "identity": "Призванный ОЯШ из Коносубы",
                "role": "Крафтер/Курьер с 100% Удачей",
                "location": "Торговая площадь ярмарки осколков",
                "equipped": ["Хорадримский Куб (S)", "Очки-оценки (S)"] if cutoff_seq >= 188 else ["Хорадримский Куб (S)"]
            }

        if cutoff_seq >= 188:
            active_chars["Фея"] = {
                "identity": "Торговка пыльцой на окраине площади ярмарки",
                "size_cm": 20,
                "attitude_to_kazuma": "Шантаж и вымогательство встречи с Боссом"
            }

        # 5. Point-in-time world conditions
        world_conditions = {
            "current_phase": "Pre-apocalypse / Early Grind" if cutoff_seq < 100 else "Pre-apocalypse / Grind and Trade Fair",
            "time_to_canon_fujimi_surge": "~1 school year",
            "primary_dimension": "Highschool of the Dead",
            "subordinate_dimension": "Shard Trade Fair (Ярмарка Осколков)" if cutoff_seq >= 140 else "None (не открыта)"
        }

        raw_state = {
            "through_seq": cutoff_seq,
            "threads": [t.model_dump() for t in active_threads],
            "epistemic": [e.model_dump() for e in epistemic],
            "chars": active_chars
        }
        snap_hash = hashlib.sha256(json.dumps(raw_state, sort_keys=True).encode("utf-8")).hexdigest()[:16]

        return NarrativeSnapshot(
            chapter_num=ch_num,
            through_discourse_seq=cutoff_seq,
            active_threads=active_threads,
            epistemic_states=epistemic,
            active_characters=active_chars,
            world_conditions=world_conditions,
            snapshot_hash=snap_hash
        )
