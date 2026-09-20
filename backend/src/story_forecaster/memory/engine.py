import hashlib
from typing import List, Dict, Any, Optional
from ..domain.scope import ForecastScope
from ..domain.memory import (
    NarrativeSnapshot,
    PlotThread,
    PlotThreadKind,
    PlotThreadStatus,
    CharacterEpistemicState,
    EpistemicAttitude,
    EvidenceRecord,
    EvidenceKind
)
from .reducer import EvidenceReducer

class NarrativeMemoryEngine:
    """
    Manages structured narrative state, plot threads, and Theory of Mind matrices
    under strict ForecastScope boundary constraints via deterministic evidence reduction.
    """

    def __init__(self, db_session: Optional[Any] = None):
        self._db_session = db_session
        self._threads: List[PlotThread] = []
        self._epistemic_states: List[CharacterEpistemicState] = []
        self._evidence_records: List[EvidenceRecord] = []
        self._initialize_baseline_canon_and_threads()
        self._initialize_baseline_evidence()

    def _initialize_baseline_canon_and_threads(self):
        """Pre-populates verified plot hooks and epistemic state established up to chapter 23."""
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

    def _initialize_baseline_evidence(self):
        """Populates verified baseline evidence records with exact coordinates and hashes."""
        def make_sha(text: str) -> str:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        records = [
            # Ch 1 (seq 1): Hachiman arrival and System activation
            EvidenceRecord(
                evidence_id="ev_ch1_arrival",
                kind=EvidenceKind.OBSERVED_EVENT,
                reader_availability_seq=1,
                in_story_temporal_seq=1,
                chapter_ordinal=1,
                scene_discourse_seq=1,
                start_char=0,
                end_char=85,
                fragment_sha256=make_sha("Хачиман Хикигая пробуждается в новом мире и активирует Систему Абсолютного Зла."),
                source_text="Хачиман Хикигая пробуждается в новом мире и активирует Систему Абсолютного Зла.",
                speaker=None,
                subject="Хачиман Хикигая",
                predicate="awakened_with_system",
                object_val="Система Абсолютного Зла",
                polarity=True,
                is_confirmed_world_fact=True
            ),
            # Ch 12 (seq 110): Fujimi Academy students
            EvidenceRecord(
                evidence_id="ev_ch12_fujimi_cast",
                kind=EvidenceKind.OBSERVED_EVENT,
                reader_availability_seq=110,
                in_story_temporal_seq=110,
                chapter_ordinal=12,
                scene_discourse_seq=110,
                start_char=100,
                end_char=210,
                fragment_sha256=make_sha("Комуро Такаши и Саэко Бусуджима ведут привычные школьные занятия в Академии Фудзими."),
                source_text="Комуро Такаши и Саэко Бусуджима ведут привычные школьные занятия в Академии Фудзими.",
                speaker=None,
                subject="Такаши Комуро",
                predicate="school_attendance",
                object_val="Академия Фудзими",
                polarity=True,
                is_confirmed_world_fact=True
            ),
            # Ch 15 (seq 140): Shard Trade Fair unlocked
            EvidenceRecord(
                evidence_id="ev_ch15_trade_fair",
                kind=EvidenceKind.NARRATOR_ASSERTION,
                reader_availability_seq=140,
                in_story_temporal_seq=140,
                chapter_ordinal=15,
                scene_discourse_seq=140,
                start_char=50,
                end_char=150,
                fragment_sha256=make_sha("Открывается портал на межпространственную Ярмарку Осколков."),
                source_text="Открывается портал на межпространственную Ярмарку Осколков.",
                speaker=None,
                subject="Хачиман Хикигая",
                predicate="unlocked_dimension",
                object_val="Ярмарка Осколков",
                polarity=True,
                is_confirmed_world_fact=True
            ),
            # Ch 22 (seq 182): Kazuma purchased and given Horadric Cube
            EvidenceRecord(
                evidence_id="ev_ch22_buy_kazuma",
                kind=EvidenceKind.OBSERVED_EVENT,
                reader_availability_seq=182,
                in_story_temporal_seq=182,
                chapter_ordinal=22,
                scene_discourse_seq=182,
                start_char=240,
                end_char=420,
                fragment_sha256=make_sha("Хачиман покупает Сато Кадзуму за 400 000 золотых и назначает его подчиненным."),
                source_text="Хачиман покупает Сато Кадзуму за 400 000 золотых и назначает его подчиненным.",
                speaker=None,
                subject="Хачиман Хикигая",
                predicate="has_subordinate",
                object_val="Сато Кадзума",
                polarity=True,
                is_confirmed_world_fact=True
            ),
            EvidenceRecord(
                evidence_id="ev_ch22_kazuma_cube",
                kind=EvidenceKind.OBSERVED_EVENT,
                reader_availability_seq=182,
                in_story_temporal_seq=182,
                chapter_ordinal=22,
                scene_discourse_seq=182,
                start_char=430,
                end_char=580,
                fragment_sha256=make_sha("Кадзума получает в распоряжение Хорадримский Куб S-ранга."),
                source_text="Кадзума получает в распоряжение Хорадримский Куб S-ранга.",
                speaker=None,
                subject="Сато Кадзума",
                predicate="equipped_with",
                object_val="Хорадримский Куб (S)",
                polarity=True,
                is_confirmed_world_fact=True
            ),
            # Ch 23 (seq 188): Kazuma Evaluation Glasses
            EvidenceRecord(
                evidence_id="ev_ch23_kazuma_glasses",
                kind=EvidenceKind.OBSERVED_EVENT,
                reader_availability_seq=188,
                in_story_temporal_seq=188,
                chapter_ordinal=23,
                scene_discourse_seq=188,
                start_char=100,
                end_char=220,
                fragment_sha256=make_sha("Кадзума надевает Очки-оценки S-ранга для проверки товаров на ярмарке."),
                source_text="Кадзума надевает Очки-оценки S-ранга для проверки товаров на ярмарке.",
                speaker=None,
                subject="Сато Кадзума",
                predicate="equipped_with",
                object_val="Очки-оценки (S)",
                polarity=True,
                is_confirmed_world_fact=True
            ),
            # Ch 23 (seq 188): Fairy appearance
            EvidenceRecord(
                evidence_id="ev_ch23_fairy_appearance",
                kind=EvidenceKind.OBSERVED_EVENT,
                reader_availability_seq=188,
                in_story_temporal_seq=188,
                chapter_ordinal=23,
                scene_discourse_seq=188,
                start_char=230,
                end_char=350,
                fragment_sha256=make_sha("Двадцатисантиметровая фея сидит на прилавке с волшебной пыльцой."),
                source_text="Двадцатисантиметровая фея сидит на прилавке с волшебной пыльцой.",
                speaker=None,
                subject="Фея",
                predicate="size_cm",
                object_val="20",
                polarity=True,
                is_confirmed_world_fact=True
            ),
            # Ch 23 (seq 188): Fairy utterance / blackmail (Dialogue - NOT a world fact!)
            EvidenceRecord(
                evidence_id="ev_ch23_fairy_blackmail_utterance",
                kind=EvidenceKind.CHARACTER_UTTERANCE,
                reader_availability_seq=188,
                in_story_temporal_seq=188,
                chapter_ordinal=23,
                scene_discourse_seq=188,
                start_char=360,
                end_char=490,
                fragment_sha256=make_sha("«Или ты ведешь меня к Боссу, или я всем расскажу про твой шест!» — пригрозила фея."),
                source_text="«Или ты ведешь меня к Боссу, или я всем расскажу про твой шест!» — пригрозила фея.",
                speaker="Фея",
                subject="Сато Кадзума",
                predicate="under_blackmail",
                object_val="разоблачение перед ярмаркой",
                polarity=True,
                is_confirmed_world_fact=False  # Utterance does not make it an objective world truth
            )
        ]
        self._evidence_records.extend(records)

    def add_evidence(self, record: EvidenceRecord) -> None:
        """Appends an evidence record to the memory ledger."""
        self._evidence_records.append(record)

    def get_evidence(self, cutoff_seq: Optional[int] = None) -> List[EvidenceRecord]:
        """Returns all evidence records permitted up to cutoff_seq."""
        if cutoff_seq is None:
            return list(self._evidence_records)
        return [ev for ev in self._evidence_records if ev.reader_availability_seq <= cutoff_seq]

    def get_snapshot(self, scope: ForecastScope) -> NarrativeSnapshot:
        """
        Builds a point-in-time narrative state snapshot filtered strictly
        by the maximum discourse sequence permitted by scope via EvidenceReducer.
        """
        cutoff_seq = scope.target_max_discourse_seq
        return EvidenceReducer.reduce(
            cutoff_seq=cutoff_seq,
            evidence_records=self._evidence_records,
            threads=self._threads,
            epistemic_states=self._epistemic_states,
            db_session=self._db_session
        )
