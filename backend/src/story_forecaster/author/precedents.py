from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from ..domain.scope import ForecastScope

class AuthorTransition(BaseModel):
    """
    Abstracted transition rule: Situation -> Resolution -> Consequence
    extracted from author N.B.'s bibliography.
    """
    transition_id: str
    source_work: str
    abstract_situation: str
    author_resolution: str
    consequence: str
    applicability_tags: List[str]

class AuthorTropeProfile(BaseModel):
    """
    Narrative fingerprint of author N.B. derived from his ~50M char corpus.
    """
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
    """Library of verified authorial precedents across N.B.'s works."""

    def __init__(self):
        self._transitions: List[AuthorTransition] = [
            AuthorTransition(
                transition_id="trans_extortion_counterplay",
                source_work="NB-neudacha / NB-obnovlennyy-mir",
                abstract_situation="Второстепенный персонаж или торговец пытается вымогать ресурсы или шантажировать протагониста/подчиненного.",
                author_resolution="Протагонист не уступает давлению; использует Систему, чтобы вскрыть слабости вымогателя и навязать ему кабальные условия сотрудничества.",
                consequence="Вымогатель превращается в зависимого поставщика или должника.",
                applicability_tags=["fairy_blackmail", "trade", "extortion", "subordinates"]
            ),
            AuthorTransition(
                transition_id="trans_subordinate_blunder_escalation",
                source_work="NB-neudacha (Book 3)",
                abstract_situation="Комический подчиненный совершает косяк из-за жадности/страха и пытается его скрыть от Босса.",
                author_resolution="Попытка скрыть косяк приводит к еще более нелепой эскалации, после чего Босс раскрывает обман и назначает штрафные работы.",
                consequence="Ситуация оборачивается юмористическим наказанием и новой выгодой для базы.",
                applicability_tags=["kazuma_blunder", "comedy", "blackmail"]
            ),
            AuthorTransition(
                transition_id="trans_canon_derailment_preparation",
                source_work="NB_Neudachnyiy_vyibor_3_V_poiskah_Silyi_ili_kanon_davay_do_svidanya",
                abstract_situation="Приближение канонического кризиса из оригинального аниме.",
                author_resolution="Герой не ждет наступления канонического события, а упреждающе перестраивает условия мира (зачищает мобов, строит базу, вербует ключевых лиц).",
                consequence="Каноническое событие срывается или происходит на условиях протагониста.",
                applicability_tags=["dungeon_surge", "hotd_apocalypse", "canon_derailment"]
            ),
            AuthorTransition(
                transition_id="trans_interlude_native_shock",
                source_work="NB - 1 - Смертельная Игра / По ту сторону Врат",
                abstract_situation="Завершение внутреннего цикла прокачки протагониста.",
                author_resolution="Глава-интерлюдия от лица аборигенов канона, которые замечают косвенные аномальные следы деятельности героя.",
                consequence="Создается предвкушение будущего прямого столкновения героя с каноническим кастом.",
                applicability_tags=["interlude", "fujimi_academy", "saeko_pov"]
            )
        ]

    def query_precedents(self, scope: ForecastScope, tags: List[str]) -> List[AuthorTransition]:
        """Retrieves relevant author transitions matching narrative tags."""
        matched = []
        for t in self._transitions:
            if any(tag in t.applicability_tags for tag in tags):
                matched.append(t)
        return matched if matched else self._transitions[:2]

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

