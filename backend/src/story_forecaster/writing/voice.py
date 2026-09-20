from typing import Dict, List, Optional
from story_forecaster.domain.writing import CharacterVoiceProfile

class VoiceRegistry:
    """
    Manages curated character voice profiles for prose synthesis.
    Encodes distinct vocabulary tone, dialogue mannerisms, sentence lengths, and interpersonal shifts.
    """

    def __init__(self):
        self._profiles: Dict[str, CharacterVoiceProfile] = {}
        self._initialize_baseline_voices()

    def _initialize_baseline_voices(self):
        self._profiles["Хачиман Хикигая"] = CharacterVoiceProfile(
            character_id="Хачиман Хикигая",
            vocabulary_tone="циничный, прагматичный, саркастичный, системно-аналитический",
            typical_sentence_length="medium",
            dialogue_mannerisms=[
                "Холодная ирония и отсылки к правилам рационального эгоизма",
                "Скептические вздохи и пресечение пафоса собеседников",
                "Слом четвертой стены во внутреннем монологе",
                "Сухой деловой тон при заключении сделок"
            ],
            interpersonal_nuance={
                "Сато Кадзума": "Снисходительно-требовательный тон Босса, осаживающий панику и бахвальство",
                "Фея": "Холодный расчетливый прессинг, давление фактами и системными условиями",
                "Саэко Бусуджима": "Сдержанно-вежливый, дистанцированный тон с уважением к ее силе",
                "Комачи Хикигая": "Заботливый, ответственный старший брат под маской ворчливости"
            },
            author_tuning_rationale="Воспроизводит авторский стиль N.B.: циничный попавший в тело Хачимана прагматик, использующий лазейки Системы Зла."
        )

        self._profiles["Сато Кадзума"] = CharacterVoiceProfile(
            character_id="Сато Кадзума",
            vocabulary_tone="разговорный, трусливо-хитрый, импульсивный, с отаку-жаргоном",
            typical_sentence_length="short",
            dialogue_mannerisms=[
                "Панические внутренние вопли при малейшей угрозе комфорту или жизни",
                "Мгновенный переход от бахвальства к угодничеству перед сильными",
                "Жалобы на тяжелую судьбу и несправедливость мира",
                "Использование обращений 'Босс', 'Шеф' с подчеркнутым подобострастием"
            ],
            interpersonal_nuance={
                "Хачиман Хикигая": "Искренний трепет перед жестокостью Системы, поиск одобрения и выгоды",
                "Фея": "Ярость от шантажа, смешанная с паническим страхом сексуального позора",
                "Торговцы ярмарки": "Высокомерное надувание щек с демонстрацией редких артефактов"
            },
            author_tuning_rationale="Канонический Кадзума из Коносубы: оппортунист и трус, чья безумная удача служит двигателем крафта."
        )

        self._profiles["Фея"] = CharacterVoiceProfile(
            character_id="Фея",
            vocabulary_tone="пискляво-наглый, вымогательский, торгово-жадный",
            typical_sentence_length="short",
            dialogue_mannerisms=[
                "Шантаж интимными или позорными слухами с ехидным хихиканьем",
                "Раздувание собственной значимости несмотря на 20-сантиметровый рост",
                "Резкая смена тона на жалобный писк при демонстрации подавляющей силы"
            ],
            interpersonal_nuance={
                "Сато Кадзума": "Безжалостный шантаж и насмешки над его 'шестом'",
                "Хачиман Хикигая": "Попытка наглеть сменяется ужасом перед аурой истинного Зла"
            },
            author_tuning_rationale="Комический триггер сюжета главы 23–24 у N.B.: мелкая вымогательница, нарывающаяся на системного монстра."
        )

        self._profiles["Саэко Бусуджима"] = CharacterVoiceProfile(
            character_id="Саэко Бусуджима",
            vocabulary_tone="традиционно-вежливый, благородный, сдержанный, острый",
            typical_sentence_length="compound",
            dialogue_mannerisms=[
                "Вежливые японские почтительные формы кэйдго",
                "Хладнокровные краткие реплики в бою",
                "Внимательное наблюдение за аномалиями в поведении Хачимана"
            ],
            interpersonal_nuance={
                "Хачиман Хикигая": "Уважительный интерес к его необычной силе и странному спокойствию",
                "Такаши Комуро": "Дружеская дистанция капитанши клуба"
            },
            author_tuning_rationale="Канон HOTD: старшеклассница-мечница с самурайским воспитанием и скрытой тягой к насилию."
        )

    def get_profile(self, character_id: str) -> Optional[CharacterVoiceProfile]:
        """Returns voice profile for character if registered."""
        return self._profiles.get(character_id)

    def get_profiles_for(self, character_ids: List[str]) -> List[CharacterVoiceProfile]:
        """Returns voice profiles for all specified characters that exist in registry."""
        return [self._profiles[cid] for cid in character_ids if cid in self._profiles]

    def register_profile(self, profile: CharacterVoiceProfile) -> None:
        """Registers or overrides a character voice profile."""
        self._profiles[profile.character_id] = profile

    def list_characters(self) -> List[str]:
        """Returns list of registered character names."""
        return list(self._profiles.keys())

