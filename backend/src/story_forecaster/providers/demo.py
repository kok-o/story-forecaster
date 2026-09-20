import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List
from .base import BaseLLMProvider
from ..domain.scope import ForecastScope
from ..domain.forecast import (
    ForecastResult,
    PredictionCandidate,
    ChapterTopology,
    PlotBeat,
    NarrativeMode
)
from ..domain.canon import ReferenceClassification

class DemoProvider(BaseLLMProvider):
    """
    Deterministic offline provider.
    Allows full end-to-end testing of migrations, data flow, scoping,
    and CLI orchestration without needing external API tokens.
    """

    def classify_reference(self, entity_text: str, context_sentence: str) -> ReferenceClassification:
        lower_entity = entity_text.lower()
        if "коносуба" in lower_entity or "аква" in lower_entity or "кадзума" in lower_entity:
            return ReferenceClassification.CROSSOVER_ENTITY
        elif "хорадрим" in lower_entity or "диабло" in lower_entity or "куб" in lower_entity:
            return ReferenceClassification.BORROWED_MECHANIC
        elif "минато" in lower_entity or "хокаге" in lower_entity:
            return ReferenceClassification.QUOTE_OR_JOKE
        elif "саэко" in lower_entity or "такаши" in lower_entity or "рэй" in lower_entity or "зомби" in lower_entity:
            return ReferenceClassification.PRIMARY_CANON
        return ReferenceClassification.AMBIGUOUS

    def generate_hypotheses(
        self,
        scope: ForecastScope,
        target_context: Dict[str, Any],
        author_precedents: List[Dict[str, Any]],
        canon_context: List[Dict[str, Any]],
        num_candidates: int = 3
    ) -> ForecastResult:
        cutoff = scope.target_max_discourse_seq
        now_str = datetime.now(timezone.utc).isoformat()
        scope_hash = hashlib.sha256(scope.model_dump_json().encode("utf-8")).hexdigest()[:16]

        chapter_num = target_context.get("chapter_num")
        if not chapter_num:
            chapter_num = 22 if cutoff <= 184 else 23

        if cutoff <= 184:
            # Backtest mode: Predicting Chapter 23 from Chapter 22 cutoff
            c1 = PredictionCandidate(
                candidate_id="cand_ch23_kazuma_craft",
                title="Призыв Сато Кадзумы: Эксплуатация 100% Удачи в Хорадримском Кубе",
                topology=ChapterTopology(
                    pov_character="Хачиман Хикигая / Сато Кадзума",
                    narrative_mode=NarrativeMode.AFTERMATH,
                    is_direct_continuation=True,
                    focal_thread_id="thread_kazuma_fairy_dust",
                    estimated_pacing="medium"
                ),
                key_events=[
                    PlotBeat(
                        ordinal=1,
                        summary="Хачиман покупает в магазине Системы и призывает Сато Кадзуму за 400 000 золота ради 100% удачи в крафте.",
                        participants=["Хачиман Хикигая", "Сато Кадзума"],
                        conflict_type="Вербовка и подписание контракта",
                        epistemic_change="Кадзума узнает о контракте, еде за службу и статусе рабочего."
                    ),
                    PlotBeat(
                        ordinal=2,
                        summary="Хачиман привязывает к Кадзуме Хорадримский Куб и камень способности 'Духовно-фамильярное оружие', проверяя трансмутацию ядер.",
                        participants=["Хачиман Хикигая", "Сато Кадзума"],
                        conflict_type="Испытание крафта",
                        epistemic_change="Кадзума становится оператором Куба с суммарной удачей 150%."
                    ),
                    PlotBeat(
                        ordinal=3,
                        summary="Сато Кадзума отправляется на ярмарку системного осколка искать редкие ингредиенты и крафтовые рецепты.",
                        participants=["Сато Кадзума"],
                        conflict_type="Исследование рынка",
                        epistemic_change="Кадзума находит торговцев пыльцой и бахвалится своим статусом."
                    ),
                    PlotBeat(
                        ordinal=4,
                        summary="Столкновение и шантаж феи с Кадзумой на ярмарке: фея требует аудиенции с Боссом под угрозой позора.",
                        participants=["Сато Кадзума", "Фея"],
                        conflict_type="Вымогательство и шантаж",
                        epistemic_change="Кадзума оказывается перед дилеммой между гневом Босса и позором на ярмарке."
                    )
                ],
                character_motivations={
                    "Хачиман Хикигая": "Получить надежного и удачливого оператора для Хорадримского Куба без переплаты.",
                    "Сато Кадзума": "Выжить, получать вкусную еду и избежать рабства на дне фэнтези-мира.",
                    "Фея": "Заполучить оптового богатого покупателя на пыльцу фей."
                },
                potential_twist="Кадзума хвалится перед торговкой выданными ему артефактами, привлекая опасное внимание.",
                confidence_label="HIGH (Прямое продолжение покупки Куба и поиска крафтера с высокой удачей)",
                rationale="В конце главы 22 Хачиман рассчитал необходимость специализированного оператора для Куба, а Кадзума обладает максимальным статом удачи.",
                assumptions=["В магазине Системы доступна покупка персонажей за 400 000 золота."],
                continuity_verified=False,
                verification_notes="Синтетический шаблон: проверка модели и непротиворечивости не проводилась"
            )

            c2 = PredictionCandidate(
                candidate_id="cand_ch23_meron_auction",
                title="Развертывание торговли: Маски животных и аукцион извращений",
                topology=ChapterTopology(
                    pov_character="Мэрон-чан / Хачиман Хикигая",
                    narrative_mode=NarrativeMode.POLITICS,
                    is_direct_continuation=True,
                    focal_thread_id="thread_meron_suika_trade",
                    estimated_pacing="medium"
                ),
                key_events=[
                    PlotBeat(
                        ordinal=1,
                        summary="Мэрон-чан организует закрытый анонимный аукцион по продаже хентайных особенностей в родном мире.",
                        participants=["Мэрон-чан", "Суика-чан"],
                        conflict_type="Организация тайных торгов",
                        epistemic_change="Получен колоссальный приток ядер ранга E и F."
                    ),
                    PlotBeat(
                        ordinal=2,
                        summary="Попытка местной благородной семьи наехать на лавку и сорвать куш.",
                        participants=["Мэрон-чан", "Охотники-защитники"],
                        conflict_type="Рэкет и отпор",
                        epistemic_change="Демонстрация покровительства великого господина."
                    ),
                    PlotBeat(
                        ordinal=3,
                        summary="Хачиман пересчитывает прибыль и инвестирует в расширение склада.",
                        participants=["Хачиман Хикигая"],
                        conflict_type="Экономическое планирование",
                        epistemic_change="Накоплен капитал на покупку новых системных модулей."
                    )
                ],
                character_motivations={
                    "Мэрон-чан": "Доказать свою полезность Великому Благородному Господину."
                },
                potential_twist="Аукцион привлекает внимание Великих Благородных Семей.",
                confidence_label="MODERATE",
                rationale="Линия аукциона была подробно обсуждена в главе 22.",
                assumptions=["Аукцион можно провести без немедленного вмешательства патриархов."],
                continuity_verified=False,
                verification_notes="Синтетический шаблон: проверка модели и непротиворечивости не проводилась"
            )

            c3 = PredictionCandidate(
                candidate_id="cand_ch23_fujimi_fortress",
                title="Возвращение в Фудзими: Подготовка фортификаций и крафт Комачи",
                topology=ChapterTopology(
                    pov_character="Хачиман Хикигая",
                    narrative_mode=NarrativeMode.AFTERMATH,
                    is_direct_continuation=False,
                    focal_thread_id="thread_hotd_primary_world",
                    estimated_pacing="deliberate"
                ),
                key_events=[
                    PlotBeat(
                        ordinal=1,
                        summary="Хачиман возвращается в мир Школы Мертвецов и проверяет маскировку убежища.",
                        participants=["Хачиман Хикигая"],
                        conflict_type="Конспирация",
                        epistemic_change="Убежище признано готовым к приему оборудования."
                    ),
                    PlotBeat(
                        ordinal=2,
                        summary="Модернизация машинки смерти Комачи купленными ядрами и духовно-фамильярными камнями.",
                        participants=["Хачиман Хикигая", "Комачи (дроны)"],
                        conflict_type="Апгрейд боевой техники",
                        epistemic_change="Боевая мощь дистанционных турелей увеличена втрое."
                    ),
                    PlotBeat(
                        ordinal=3,
                        summary="Скрытая разведка окрестностей Академии Фудзими перед началом нового учебного семестра.",
                        participants=["Хачиман Хикигая"],
                        conflict_type="Разведка",
                        epistemic_change="Зафиксированы первые подземные эманации маны в катакомбах школы."
                    )
                ],
                character_motivations={
                    "Хачиман Хикигая": "Не допустить гибели в первый день прорыва Данжа."
                },
                potential_twist="В школьном совете Фудзими появляется подозрительный новый переводной ученик.",
                confidence_label="MODERATE",
                rationale="Подготовка к прорыву в Фудзими — магистральная цель героя.",
                assumptions=["Хачиман решает сделать паузу в покупках на межмировых ярмарках."],
                continuity_verified=False,
                verification_notes="Синтетический шаблон: проверка модели и непротиворечивости не проводилась"
            )

            return ForecastResult(
                target_work="Система Абсолютного З.Л.А.",
                cutoff_chapter=chapter_num,
                candidates=[c1, c2, c3][:num_candidates],
                author_precedent_citations=[
                    "NB-neudacha: Book 3 (утилитарное использование подчиненных ради скрытых бонусов Системы)",
                    "NB-obnovlennyy-mir: Chapter 18 (эксплуатация читерской удачи)"
                ],
                generated_at_utc=now_str,
                scope_manifest_hash=scope_hash,
                provider="demo",
                is_synthetic_demonstration=True
            )

        # Prospective mode: Predicting Chapter 24 from Chapter 23 cutoff
        c1 = PredictionCandidate(
            candidate_id="cand_1_hachiman_commercial",
            title="Коммерческий контрудар: Встреча Босса с Феей",
            topology=ChapterTopology(
                pov_character="Хачиман Хикигая",
                narrative_mode=NarrativeMode.POLITICS,
                is_direct_continuation=True,
                focal_thread_id="thread_kazuma_fairy_dust",
                estimated_pacing="medium"
            ),
            key_events=[
                PlotBeat(
                    ordinal=1,
                    summary="Кадзума в холодном поту приводит нахальную фею к Хачиману, пытаясь выставить это как грандиозную дипломатическую победу.",
                    participants=["Сато Кадзума", "Фея", "Хачиман Хикигая"],
                    conflict_type="Бюрократическое и психологическое противостояние",
                    epistemic_change="Хачиман узнает о существовании монополии на пыльцу фей на ярмарке."
                ),
                PlotBeat(
                    ordinal=2,
                    summary="Фея пытается шантажировать и завышать цену, но сталкивается с предельным цинизмом Хачимана и его Системой оценки.",
                    participants=["Фея", "Хачиман Хикигая"],
                    conflict_type="Торговый торг",
                    epistemic_change="Фея понимает, что перед ней не наивный попаданец, а безжалостный эксплуататор."
                ),
                PlotBeat(
                    ordinal=3,
                    summary="Хачиман оформляет кабальный контракт на поставку оптовой партии пыльцы в обмен на защиту и редкие ресурсы Системы.",
                    participants=["Хачиман Хикигая", "Фея"],
                    conflict_type="Заключение сделки",
                    epistemic_change="Получен ключевой ингредиент для Хорадримского Кубического Конструирования."
                )
            ],
            character_motivations={
                "Хачиман Хикигая": "Получить пыльцу для крафта артефактов без переплаты, наказать Кадзуму за самодеятельность.",
                "Сато Кадзума": "Спасти свою репутацию от позорного разоблачения и избежать наказания от Босса.",
                "Фея": "Найти постоянного богатого покупателя и сорвать куш."
            },
            potential_twist="Фея оказывается беглянкой от местного синдиката гномов-ростовщиков, что привлекает внимание к лавке Хачимана.",
            confidence_label="HIGH (Соответствует типичному паттерну N.B. по циничному переигрыванию вымогателей)",
            rationale="В работах N.B. попытки внешних персонажей развести протагониста на деньги всегда оборачиваются их собственным закабалением через лазейки Системы.",
            assumptions=["Хачиман находится в своем поместье/убежище и доступен для визита Кадзумы."],
            continuity_verified=False,
            verification_notes="Синтетический шаблон: проверка модели и непротиворечивости не проводилась"
        )

        c2 = PredictionCandidate(
            candidate_id="cand_2_kazuma_desperate_gamble",
            title="Отчаянный финт Кадзумы: Побег через Хорадримский Куб",
            topology=ChapterTopology(
                pov_character="Сато Кадзума",
                narrative_mode=NarrativeMode.ACTION,
                is_direct_continuation=True,
                focal_thread_id="thread_kazuma_fairy_dust",
                estimated_pacing="fast"
            ),
            key_events=[
                PlotBeat(
                    ordinal=1,
                    summary="Кадзума притворно соглашается вести фею к боссу, но судорожно ищет способ нейтрализовать угрозу шантажа по дороге.",
                    participants=["Сато Кадзума", "Фея"],
                    conflict_type="Попытка обмана",
                    epistemic_change="Кадзума вспоминает скрытое свойство выданного ему Куба."
                ),
                PlotBeat(
                    ordinal=2,
                    summary="Используя внезапную суматоху на краю пустыря, Кадзума активирует экспериментальный крафт и временно запирает фею в карманном пространстве.",
                    participants=["Сато Кадзума", "Фея"],
                    conflict_type="Внезапный тактический трюк",
                    epistemic_change="Шантаж временно блокирован, но возникает риск поломки артефакта."
                ),
                PlotBeat(
                    ordinal=3,
                    summary="Кадзума в панике бежит на доклад к Хачиману с 'трофеем', надеясь, что ценность запертой феи перевесит косяк.",
                    participants=["Сато Кадзума"],
                    conflict_type="Бегство от последствий",
                    epistemic_change="Фея в ловушке обещает страшную месть."
                )
            ],
            character_motivations={
                "Сато Кадзума": "Любой ценой заткнуть рот фее до того, как слухи о его 'шесте' дойдут до ярмарки."
            },
            potential_twist="Заточение феи нарушает законы нейтралитета торговой ярмарки осколков, вызывая тревогу охраны.",
            confidence_label="MODERATE (Типичный для Кадзумы стиль решения проблем через авантюры, приводящие к новым катастрофам)",
            rationale="Кадзума в каноне KonoSuba и адаптации N.B. регулярно совершает хаотичные поступки, усугубляющие ситуацию.",
            assumptions=["Артефакт Куба способен удерживать живое существо ранга F/E."],
            continuity_verified=False,
            verification_notes="Синтетический шаблон: проверка модели и непротиворечивости не проводилась"
        )

        c3 = PredictionCandidate(
            candidate_id="cand_3_interlude_fujimi_peace",
            title="Интерлюдия: Подозрения в Академии Фудзими",
            topology=ChapterTopology(
                pov_character="Сая Такаги",
                narrative_mode=NarrativeMode.INTERLUDE,
                is_direct_continuation=False,
                focal_thread_id="thread_hotd_primary_world",
                estimated_pacing="medium"
            ),
            key_events=[
                PlotBeat(
                    ordinal=1,
                    summary="Смена точки зрения на Академию Фудзими: Сая Такаги раздражена регулярными прогулами и странным циничным поведением одноклассника Хачимана Хикигая.",
                    participants=["Сая Такаги", "Саэко Бусуджима", "Коити Сидо"],
                    conflict_type="Социальное подозрение и наблюдение",
                    epistemic_change="Сая замечает, что нищий нелюдим внезапно снял престижную квартиру и закупает дорогостоящее снаряжение."
                ),
                PlotBeat(
                    ordinal=2,
                    summary="В клубе кэндо Саэко Бусуджима делится ощущением опасной ауры, исходящей от Хачимана при редких встречах в коридорах.",
                    participants=["Саэко Бусуджима", "Сая Такаги"],
                    conflict_type="Анализ скрытой силы",
                    epistemic_change="Саэко интуитивно чувствует в Хачимане хищника, прошедшего смертельные бои."
                ),
                PlotBeat(
                    ordinal=3,
                    summary="Коити Сидо пытается инициировать дисциплинарное расследование против Хачимана, чтобы выслужиться перед дирекцией школы.",
                    participants=["Коити Сидо"],
                    conflict_type="Бюрократическая интрига",
                    epistemic_change="В школе назревает административный конфликт к возвращению Хачимана."
                )
            ],
            character_motivations={
                "Сая Такаги": "Удовлетворить уязвленное самолюбие и разгадать секрет странного одноклассника.",
                "Саэко Бусуджима": "Понять природу скрытой жажды крови и боевой ауры Хачимана.",
                "Коити Сидо": "Найти компромат для давления и подчинения непокорного ученика."
            },
            potential_twist="Разведка Сидо случайно натыкается на следы печатей у входа в подземный катакомбный Данж школы.",
            confidence_label="MODERATE (N.B. регулярно вставляет интерлюдии школьной верхушки для контраста масштабов мышления)",
            rationale="В цикле «Неудачный выбор» N.B. систематически показывает школьное окружение, строящее конспирологические теории вокруг главного героя, пока тот занят системным фармом.",
            assumptions=["В мире HOTD продолжается мирный период за ~1 год до Прорыва Подземелья."],
            continuity_verified=False,
            verification_notes="Синтетический шаблон: проверка модели и непротиворечивости не проводилась"
        )

        return ForecastResult(
            target_work="Система Абсолютного З.Л.А.",
            cutoff_chapter=chapter_num,
            candidates=[c1, c2, c3][:num_candidates],
            author_precedent_citations=[
                "NB-neudacha: Book 3 (канон давай до свидания, переигрывание шантажистов)",
                "NB-obnovlennyy-mir: Chapter 14 (циничный контракт с вымогателями)"
            ],
            generated_at_utc=now_str,
            scope_manifest_hash=scope_hash,
            provider="demo",
            is_synthetic_demonstration=True
        )
