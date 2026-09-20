from typing import Dict
from story_forecaster.evaluation.schemas import GoldChapterData, EventUnit

CHAPTER_23_GOLD = GoldChapterData(
    chapter_ordinal=23,
    title="Глава 23",
    pov_character="Хачиман Хикигая / Сато Кадзума",
    narrative_mode="AFTERMATH",
    key_events=[
        EventUnit(
            actor="Хачиман Хикигая",
            action="покупает в магазине Системы и призывает Сато Кадзуму за 400 000 золота ради 100% удачи",
            target="Сато Кадзума (KonoSuba)",
            outcome="Кадзума завербован через рабочий контракт, сытное бенто и обещание перспектив",
            polarity=True,
            modality="occurred",
            causal_links=["подготовка к крафту", "покупка Хорадримского Куба"],
            negative_examples=[
                "Хачиман отказался от призыва",
                "покупка Кадзумы сорвана",
                "Кадзума убит до контракта",
                "призыв провалился",
                "Кадзума отверг предложение"
            ]
        ),
        EventUnit(
            actor="Хачиман Хикигая",
            action="привязывает к Кадзуме Хорадримский Куб, камень способности 'Духовно-фамильярное оружие' и скармливает тыблоко ранга D+",
            target="Сато Кадзума",
            outcome="Кадзума становится оператором Куба с суммарной удачей крафта 150% и получает квартиру в Фудзими",
            polarity=True,
            modality="occurred",
            causal_links=["завершение призыва", "расширение производственной базы"],
            negative_examples=[
                "Куб уничтожен",
                "Куб сломан",
                "Куб утерян",
                "Хачиман оставил Куб себе",
                "передача Куба не состоялась"
            ]
        ),
        EventUnit(
            actor="Сато Кадзума",
            action="осваивает трансмутацию в Хорадримском Кубе и проверяет формулы слияния ядер и артефактов",
            target="Хорадримский Куб / Системные ядра",
            outcome="подтверждена колоссальная экономия прочности благодаря сверхвысокой удаче",
            polarity=True,
            modality="occurred",
            causal_links=["привязка Куба"],
            negative_examples=[
                "крафт невозможен",
                "Куб взорвался",
                "крафт провалился",
                "трансмутация не работает"
            ]
        ),
        EventUnit(
            actor="Сато Кадзума",
            action="отправляется на ярмарку системного осколка на разведку ингредиентов (пыльца фей, сырье)",
            target="Торговцы ярмарки межмирья",
            outcome="хвалится перед торговцами своим статусом и демонстрирует очки оценки и Куб",
            polarity=True,
            modality="occurred",
            causal_links=["поиск компонентов для Куба"],
            negative_examples=[
                "ярмарка закрыта",
                "ярмарка уничтожена",
                "Кадзума остался дома",
                "отказ от разведки"
            ]
        ),
        EventUnit(
            actor="Фея-торговка",
            action="шантажирует Кадзуму угрозой публичного сексуального позора на всей ярмарке",
            target="Сато Кадзума",
            outcome="требует немедленно организовать встречу с его Боссом (Хачиманом) ради оптовых контрактов на пыльцу",
            polarity=True,
            modality="occurred",
            causal_links=["демонстрация очков оценки и бахвальство Кадзумы"],
            negative_examples=[
                "фея подарила пыльцу бесплатно",
                "фея сбежала",
                "фея убита Кадзумой",
                "шантаж не состоялся",
                "Кадзума убил фею"
            ]
        )
    ],
    active_threads=[
        "Линия Кадзумы: оператор Куба и торговля на ярмарке",
        "Линия подготовки к Прорыву Подземелья в Академии Фудзими",
        "Шантаж феи и угроза разоблачения базы Хачимана"
    ],
    cliffhanger="Фея угрожает опозорить Кадзуму на площади ложью о его мужской несостоятельности, если тот не приведет ее к хозяину."
)

CHAPTER_24_GOLD = GoldChapterData(
    chapter_ordinal=24,
    title="Глава 24",
    pov_character="Хачиман Хикигая",
    narrative_mode="POLITICS",
    key_events=[
        EventUnit(
            actor="Сато Кадзума",
            action="приводит фею-шантажистку на конспиративную квартиру к Хачиману",
            target="Хачиман Хикигая",
            outcome="Хачиман оценивает угрозу раскрытия базы и берёт переговоры под личный контроль",
            polarity=True,
            modality="occurred",
            causal_links=["шантаж феи на ярмарке", "демонстрация очков оценки"],
            negative_examples=[
                "Кадзума скрыл фею от Хачимана",
                "фея отказалась идти к Боссу",
                "Хачиман выгнал фею не слушая"
            ]
        ),
        EventUnit(
            actor="Хачиман Хикигая",
            action="вступает в жесткие переговоры с феей, используя цинизм и системную оценку для сбивания цены",
            target="Фея-торговка",
            outcome="фея подавлена психологически и теряет рычаги шантажа",
            polarity=True,
            modality="occurred",
            causal_links=["попытка шантажа Босса"],
            negative_examples=[
                "Хачиман поддался на шантаж",
                "переговоры провалились",
                "фея обманула Хачимана"
            ]
        ),
        EventUnit(
            actor="Хачиман Хикигая",
            action="заключает кабальный оптовый контракт на поставку пыльцы фей по демпинговой цене",
            target="Фея-торговка",
            outcome="обеспечен постоянный канал редких ингредиентов для Хорадримского Куба и производства",
            polarity=True,
            modality="occurred",
            causal_links=["подавление шантажа", "завершение торговой сделки"],
            negative_examples=[
                "сделка сорвана",
                "контракт не заключен",
                "фея отказалась поставлять пыльцу"
            ]
        )
    ],
    active_threads=[
        "Линия пыльцы фей и Хорадримского Куба",
        "Линия подготовки к Академии Фудзими"
    ],
    cliffhanger="Внимание местных торговых синдикатов привлечено к появлению крупных объемов пыльцы фей."
)

BENCHMARK_REGISTRY: Dict[int, GoldChapterData] = {
    23: CHAPTER_23_GOLD,
    24: CHAPTER_24_GOLD
}

def get_gold_chapter(chapter_num: int) -> GoldChapterData:
    """Retrieves gold reference for the specified chapter."""
    if chapter_num not in BENCHMARK_REGISTRY:
        available = sorted(list(BENCHMARK_REGISTRY.keys()))
        raise ValueError(
            f"No benchmark gold data registered for chapter {chapter_num}. "
            f"Available benchmark chapters: {available}."
        )
    return BENCHMARK_REGISTRY[chapter_num]
