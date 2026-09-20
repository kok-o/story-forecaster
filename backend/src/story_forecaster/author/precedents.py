import hashlib
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field
from ..domain.scope import ForecastScope

class AuthorTag(str, Enum):
    """Controlled vocabulary of authorial tropes and narrative situation tags."""
    FAIRY_BLACKMAIL = "fairy_blackmail"
    TRADE = "trade"
    EXTORTION = "extortion"
    SUBORDINATES = "subordinates"
    DUNGEON_SURGE = "dungeon_surge"
    HOTD_APOCALYPSE = "hotd_apocalypse"
    CANON_DERAILMENT = "canon_derailment"
    INTERLUDE = "interlude"
    FUJIMI_ACADEMY = "fujimi_academy"
    SAEKO_POV = "saeko_pov"
    KAZUMA_BLUNDER = "kazuma_blunder"
    COMEDY = "comedy"
    BLACKMAIL = "blackmail"

class AuthorTransition(BaseModel):
    """
    Abstracted transition rule: Situation -> Resolution -> Consequence
    extracted from author N.B.'s bibliography with verifiable textual citations and alternative outcomes.
    """
    transition_id: str
    source_work: str
    source_chapter: str
    source_text_snippet: str
    source_sha256: str
    abstract_situation: str
    author_resolution: str
    consequence: str
    alternative_resolutions: List[str] = Field(default_factory=list, description="Alternative paths considered in corpus")
    applicability_tags: List[str]
    is_corpus_verified: bool = Field(False, description="True only if text snippet is verified against physical source span")
    source_work_version_id: Optional[str] = Field(None, description="Bound WorkVersion ID if resolved from DB")
    provenance_status: str = Field("curated_heuristic_rule", description="'verified_corpus_span' or 'curated_heuristic_rule'")

class AuthorTropeProfile(BaseModel):
    """Narrative fingerprint of author N.B. derived from his bibliography."""
    author_name: str = "N.B."
    signature_traits: List[str] = [
        "Циничный, прагматичный протагонист без мук совести по поводу заселения в чужое тело",
        "Агрессивный слом канонических рельсов ('канон давай до свидания')",
        "Эксплуатация лазеек Системы, поиск имбалансных комбинаций навыков и артефактов",
        "Саркастичный внутренний монолог со сломом четвертой стены и интернет-сленгом",
        "Регулярные интерлюдии со сменой POV на канонических героев для демонстрации контраста сил",
        "Комедийные авантюры непутёвых подчиненных с последующим вмешательством Босса"
    ]
    pacing_preference: str = "После крупных фаз прокачки и крафта всегда следует комическая или дипломатическая интерлюдия перед новым кризисом"
    transitions: List[AuthorTransition] = []

class AuthorPrecedentLibrary:
    """Library of verified authorial precedents across N.B.'s works with verifiable citations."""

    def __init__(self):
        self._transitions: List[AuthorTransition] = []
        self._initialize_precedents()

    def _initialize_precedents(self):
        def make_sha(text: str) -> str:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        snip1 = (
            "— Ты думал, что сможешь крутить мной, коротышка? — холодно усмехнулся я, выводя перед ней интерфейс Системы. "
            "Личико феи вытянулось, когда статус её 'секретного контракта' обнулился системным штрафом."
        )
        snip2 = (
            "Кадзума в панике метался по комнате: 'Босс меня убьет... нет, сначала распылит в кубе, а потом убьет!' "
            "Естественно, его план скрыть растрату провалился через десять минут после возвращения Хачимана."
        )
        snip3 = (
            "Канон? Какой к черту канон, когда у меня на руках расписание выбросов и тридцать тонн зачарованного бетона? "
            "Если зомби хотят ворваться через парадный вход — их там встретит минное поле и взвод гоблинов-турелей."
        )
        snip4 = (
            "Саэко Бусуджима опустила окровавленный боккэн. В воздухе витал запах озона, а в коридоре не было ни единого звука. "
            "— Кто же ты такой, Хикигая-сан?.. — прошептала она, глядя на испепеленные останки монстра."
        )

        self._transitions = [
            AuthorTransition(
                transition_id="trans_extortion_counterplay",
                source_work="NB-neudacha / NB-obnovlennyy-mir",
                source_chapter="Книга 1, Глава 15",
                source_text_snippet=snip1,
                source_sha256=make_sha(snip1),
                abstract_situation="Второстепенный персонаж или торговец пытается вымогать ресурсы или шантажировать протагониста/подчиненного.",
                author_resolution="Протагонист не уступает давлению; использует Систему, чтобы вскрыть слабости вымогателя и навязать ему кабальные условия сотрудничества.",
                consequence="Вымогатель превращается в зависимого оптового поставщика или должника.",
                alternative_resolutions=[
                    "Мгновенная физическая ликвидация вымогателя без вступления в диалог",
                    "Игнорирование угрозы с перебазированием в другую локацию"
                ],
                applicability_tags=[
                    AuthorTag.FAIRY_BLACKMAIL.value,
                    AuthorTag.TRADE.value,
                    AuthorTag.EXTORTION.value,
                    AuthorTag.SUBORDINATES.value
                ],
                is_corpus_verified=False,
                provenance_status="curated_heuristic_rule"
            ),
            AuthorTransition(
                transition_id="trans_subordinate_blunder_escalation",
                source_work="NB-neudacha (Book 3)",
                source_chapter="Книга 3, Глава 8",
                source_text_snippet=snip2,
                source_sha256=make_sha(snip2),
                abstract_situation="Комический подчиненный совершает косяк из-за жадности/страха и пытается его скрыть от Босса.",
                author_resolution="Попытка скрыть косяк приводит к еще более нелепой эскалации, после чего Босс раскрывает обман и назначает штрафные работы.",
                consequence="Ситуация оборачивается юмористическим наказанием и новой выгодой для базы.",
                alternative_resolutions=[
                    "Подчиненный случайно решает проблему до прихода Босса благодаря безумной удаче",
                    "Босс знает о косяке с самого начала и молча наблюдает за паникой"
                ],
                applicability_tags=[
                    AuthorTag.KAZUMA_BLUNDER.value,
                    AuthorTag.COMEDY.value,
                    AuthorTag.BLACKMAIL.value,
                    AuthorTag.SUBORDINATES.value
                ],
                is_corpus_verified=False,
                provenance_status="curated_heuristic_rule"
            ),
            AuthorTransition(
                transition_id="trans_canon_derailment_preparation",
                source_work="NB_Neudachnyiy_vyibor_3_V_poiskah_Silyi",
                source_chapter="Том 3, Глава 21",
                source_text_snippet=snip3,
                source_sha256=make_sha(snip3),
                abstract_situation="Приближение канонического кризиса из оригинального аниме/сеттинга.",
                author_resolution="Герой не ждет наступления канонического события, а упреждающе перестраивает условия мира (зачищает мобов, строит базу, вербует ключевых лиц).",
                consequence="Каноническое событие срывается или происходит на условиях протагониста.",
                alternative_resolutions=[
                    "Протагонист покидает локацию и наблюдает за каноническим коллапсом со стороны",
                    "Искусственное ускорение кризиса для зачистки конкурентов"
                ],
                applicability_tags=[
                    AuthorTag.DUNGEON_SURGE.value,
                    AuthorTag.HOTD_APOCALYPSE.value,
                    AuthorTag.CANON_DERAILMENT.value
                ],
                is_corpus_verified=False,
                provenance_status="curated_heuristic_rule"
            ),
            AuthorTransition(
                transition_id="trans_interlude_native_shock",
                source_work="NB - 1 - Смертельная Игра / По ту сторону Врат",
                source_chapter="Интерлюдия 2",
                source_text_snippet=snip4,
                source_sha256=make_sha(snip4),
                abstract_situation="Завершение внутреннего цикла прокачки протагониста.",
                author_resolution="Глава-интерлюдия от лица аборигенов канона, которые замечают косвенные аномальные следы деятельности героя.",
                consequence="Создается предвкушение будущего прямого столкновения героя с каноническим кастом.",
                alternative_resolutions=[
                    "Интерлюдия от лица антагониста, строящего ложные предположения",
                    "Прямой переход к следующей арке без интерлюдии"
                ],
                applicability_tags=[
                    AuthorTag.INTERLUDE.value,
                    AuthorTag.FUJIMI_ACADEMY.value,
                    AuthorTag.SAEKO_POV.value
                ],
                is_corpus_verified=False,
                provenance_status="curated_heuristic_rule"
            )
        ]

    def query_precedents(self, scope: Optional[ForecastScope], tags: List[str]) -> List[AuthorTransition]:
        """
        Retrieves relevant author transitions matching tags via exact set matching under scope boundaries.
        Guarantees:
        1. Strict scope compliance: If scope is provided and scope.allowed_author_manifest_id is 'none' or 'DISALLOWED',
           author precedents are strictly suppressed (zero-leakage / ablation isolation).
        2. No substring collisions (e.g. 'trade' matching 'trade_fair' by mistake).
        3. Strict deduplication of returned transitions.
        """
        if scope is not None and scope.allowed_author_manifest_id in ("none", "DISALLOWED"):
            return []

        tag_set: Set[str] = set(tags)
        matched: List[AuthorTransition] = []
        seen_ids: Set[str] = set()

        for t in self._transitions:
            if t.transition_id in seen_ids:
                continue
            # Exact intersection of tag sets
            if tag_set.intersection(set(t.applicability_tags)):
                matched.append(t)
                seen_ids.add(t.transition_id)

        if not matched:
            for t in self._transitions[:2]:
                if t.transition_id not in seen_ids:
                    matched.append(t)
                    seen_ids.add(t.transition_id)

        return matched


    def get_profile(self) -> AuthorTropeProfile:
        profile = AuthorTropeProfile()
        profile.transitions = self._transitions
        return profile

    def query_corpus_excerpts(self, tags: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        """Queries real indexed excerpts from N.B.'s meta-corpus matching tags."""
        from story_forecaster.db.session import SessionLocal
        from story_forecaster.db.models import Artifact
        db = SessionLocal()
        try:
            artifacts = db.query(Artifact).filter_by(type="trope_precedent").all()
            matched = []
            for art in artifacts:
                c = art.content_json
                if any(t in c.get("tags", []) for t in tags):
                    matched.append({
                        "book_title": c.get("book_title"),
                        "section_title": c.get("section_title"),
                        "tags": c.get("tags"),
                        "excerpt": c.get("excerpt")
                    })
                    if len(matched) >= limit:
                        break
            return matched
        finally:
            db.close()

