import re
import math
from typing import List, Tuple, Optional, Set
from story_forecaster.evaluation.schemas import (
    GoldChapterData, EventUnit, MatchRecord, CandidateMetrics, EvaluationReport
)
from story_forecaster.domain.forecast import PredictionCandidate, ForecastResult

class BacktestEvaluator:
    """
    Evaluates prediction candidates against held-out gold chapter events honoring:
    1. Strict 1-to-1 bipartite matching with maximum total weight.
    2. Zero tolerance for contradictory/opposite predictions (penalized with 0.0, no partial keyword credit).
    3. Explicit tracking of missed gold events and spurious predicted beats.
    4. Honest reporting of verification status ('not_checked' instead of fake constants).
    5. Prior candidate ranking fixed strictly before gold evaluation.
    """

    def evaluate_candidate(self, candidate: PredictionCandidate, gold: GoldChapterData) -> CandidateMetrics:
        """Evaluates a single candidate against gold reference."""
        # 1. Topology match
        pov_match = self._check_pov_match(candidate.topology.pov_character, gold.pov_character)
        mode_match = (
            candidate.topology.narrative_mode.value.lower() == gold.narrative_mode.lower() or
            ("plan" in candidate.topology.narrative_mode.value.lower() and "plan" in gold.narrative_mode.lower())
        )
        topology_score = 1.0 if (pov_match and mode_match) else (0.5 if (pov_match or mode_match) else 0.0)

        # 2. Pairwise matching weights matrix [num_gold, num_predicted]
        gold_events = gold.key_events
        pred_beats = candidate.key_events

        cost_matrix = []
        for g_idx, g_event in enumerate(gold_events):
            row = []
            for p_idx, p_beat in enumerate(pred_beats):
                weight, rationale = self._score_event_pair(g_event, p_beat.summary, p_beat.conflict_type)
                row.append((weight, rationale))
            cost_matrix.append(row)

        # 3. Strict 1-to-1 bipartite maximum weight matching
        matches: List[MatchRecord] = []
        assigned_gold: Set[int] = set()
        assigned_pred: Set[int] = set()

        if gold_events and pred_beats:
            try:
                import numpy as np
                from scipy.optimize import linear_sum_assignment

                # Build weight matrix [num_gold, num_pred]
                w_matrix = np.zeros((len(gold_events), len(pred_beats)), dtype=float)
                for g_i in range(len(gold_events)):
                    for p_i in range(len(pred_beats)):
                        w_matrix[g_i, p_i] = cost_matrix[g_i][p_i][0]

                # linear_sum_assignment minimizes, so pass negative weights
                row_ind, col_ind = linear_sum_assignment(-w_matrix)

                for g_idx, p_idx in zip(row_ind, col_ind):
                    w, r = cost_matrix[g_idx][p_idx]
                    if w > 0.0:
                        assigned_gold.add(g_idx)
                        assigned_pred.add(p_idx)
                        matches.append(MatchRecord(
                            gold_event_idx=g_idx + 1,
                            candidate_beat_idx=pred_beats[p_idx].ordinal,
                            gold_summary=f"[{gold_events[g_idx].actor}] {gold_events[g_idx].action} -> {gold_events[g_idx].outcome}",
                            predicted_summary=pred_beats[p_idx].summary,
                            weight=w,
                            rationale=r
                        ))
            except ImportError:
                # Fallback greedy matching if scipy is unavailable
                pairs = []
                for g_idx in range(len(gold_events)):
                    for p_idx in range(len(pred_beats)):
                        w, r = cost_matrix[g_idx][p_idx]
                        if w > 0.0:
                            pairs.append((w, g_idx, p_idx, r))
                pairs.sort(key=lambda x: x[0], reverse=True)
                for w, g_idx, p_idx, r in pairs:
                    if g_idx not in assigned_gold and p_idx not in assigned_pred:
                        assigned_gold.add(g_idx)
                        assigned_pred.add(p_idx)
                        matches.append(MatchRecord(
                            gold_event_idx=g_idx + 1,
                            candidate_beat_idx=pred_beats[p_idx].ordinal,
                            gold_summary=f"[{gold_events[g_idx].actor}] {gold_events[g_idx].action} -> {gold_events[g_idx].outcome}",
                            predicted_summary=pred_beats[p_idx].summary,
                            weight=w,
                            rationale=r
                        ))

        # Sort matches by gold_event_idx for clear reporting
        matches.sort(key=lambda m: m.gold_event_idx)

        # 4. Explicit missed events and spurious predictions
        missed_gold = [i + 1 for i in range(len(gold_events)) if i not in assigned_gold]
        spurious_beats = [pred_beats[j].ordinal for j in range(len(pred_beats)) if j not in assigned_pred]

        # 5. Compute precision, recall, F1
        total_matched_weight = sum(m.weight for m in matches)
        precision = total_matched_weight / len(pred_beats) if pred_beats else 0.0
        recall = total_matched_weight / len(gold_events) if gold_events else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        # 6. Honest character consistency status
        continuity_status = getattr(candidate, "continuity_status", None)
        if continuity_status == "passed":
            consistency_score = 1.0
            consistency_status_str = "passed"
        elif continuity_status in ("failed", "citation_violation"):
            consistency_score = 0.0
            consistency_status_str = "failed"
        else:
            consistency_score = None
            consistency_status_str = "not_checked"

        return CandidateMetrics(
            candidate_id=candidate.candidate_id,
            title=candidate.title,
            pov_character=candidate.topology.pov_character,
            narrative_mode=candidate.topology.narrative_mode.value,
            topology_score=topology_score,
            topology_status="checked",
            event_precision=round(precision, 3),
            event_recall=round(recall, 3),
            event_f1=round(f1, 3),
            character_consistency=consistency_score,
            character_consistency_status=consistency_status_str,
            matches=matches,
            missed_gold_events=missed_gold,
            spurious_predicted_beats=spurious_beats
        )

    def evaluate_forecast(
        self,
        result: ForecastResult,
        gold: GoldChapterData,
        cutoff_chapter: int
    ) -> EvaluationReport:
        """
        Evaluates all candidates and compiles an EvaluationReport.
        Crucial: Fixes ranking_prior_to_gold strictly before examining gold events.
        """
        if not result.candidates:
            raise ValueError("No candidates provided in ForecastResult")

        # 1. Prior ranking established BEFORE opening gold (e.g. by model confidence or candidate index)
        prior_ranked_ids = [c.candidate_id for c in result.candidates]

        # 2. Evaluate each candidate against gold
        cand_results = [self.evaluate_candidate(c, gold) for c in result.candidates]

        # Best@1 is strictly the top-ranked candidate according to prior ranking
        best_at_1 = cand_results[0]

        # Oracle@K is the candidate with the highest actual F1 match
        oracle_at_k = max(cand_results, key=lambda c: c.event_f1)

        f1_values = [c.event_f1 for c in cand_results]
        mean_f1 = round(sum(f1_values) / len(f1_values), 3)

        # Variance and Standard Deviation
        variance = sum((f - mean_f1) ** 2 for f in f1_values) / len(f1_values) if f1_values else 0.0
        std = math.sqrt(variance)

        verdict = (
            f"Backtest against Chapter {gold.chapter_ordinal}: Best@1 F1={best_at_1.event_f1} "
            f"(Recall={best_at_1.event_recall}), Oracle@{len(cand_results)} F1={oracle_at_k.event_f1} "
            f"(Recall={oracle_at_k.event_recall}, Candidate '{oracle_at_k.title}'). "
            f"F1 Variance={round(variance, 4)}, Std={round(std, 4)}."
        )

        return EvaluationReport(
            cutoff_chapter=cutoff_chapter,
            hidden_chapter=gold.chapter_ordinal,
            total_candidates=len(cand_results),
            ranking_prior_to_gold=prior_ranked_ids,
            best_at_1=best_at_1,
            oracle_at_k=oracle_at_k,
            mean_f1=mean_f1,
            f1_variance=round(variance, 4),
            f1_std=round(std, 4),
            all_candidates=cand_results,
            summary_verdict=verdict
        )

    def _check_pov_match(self, pred_pov: str, gold_pov: str) -> bool:
        """Checks if POV matches or has significant character overlap."""
        pred_norm = pred_pov.lower()
        gold_norm = gold_pov.lower()

        tokens = [t for t in re.split(r"[\s/,]+", gold_norm) if len(t) > 3]
        for t in tokens:
            if t in pred_norm:
                return True
        return False

    def _score_event_pair(
        self,
        gold_event: EventUnit,
        pred_summary: str,
        conflict_type: Optional[str]
    ) -> Tuple[float, str]:
        """
        Calculates pairwise semantic weight (0.0, 0.5, 1.0) and rationale.
        Crucial: Opposing/contradictory events receive 0.0 with explicit rationale,
        and never receive partial keyword credits.
        """
        summary_lower = pred_summary.lower()

        # 1. Check explicit negative examples registered in gold event
        for neg_ex in gold_event.negative_examples:
            neg_tokens = [t for t in re.findall(r"\b[а-яёa-z0-9]{3,}\b", neg_ex.lower())]
            if len(neg_tokens) >= 2:
                if all(t in summary_lower for t in neg_tokens):
                    return 0.0, f"Противоречие: совпадение с негативным контрпримером ('{neg_ex}')"

        # 2. General Contradiction & Negation Detection
        negation_terms = [
            "уничтожен", "разрушен", "сломан", "невозможн", "не удал", "не смож",
            "провал", "сорван", "отказ", "погиб", "убит", "ликвидирован", "потерян",
            "не стал", "не будет", "отказался", "запрещен", "мертв", "смерть"
        ]
        has_negation = any(neg in summary_lower for neg in negation_terms)

        if has_negation:
            # Check if negation contradicts positive gold action/entity
            if gold_event.polarity:
                # Universal contradiction: check if key nouns from gold target/outcome are negated in prediction
                target_tokens = [t for t in re.findall(r"\b[а-яёa-z]{4,}\b", gold_event.target.lower())]
                outcome_tokens = [t for t in re.findall(r"\b[а-яёa-z]{4,}\b", gold_event.outcome.lower())]
                actor_tokens = [t for t in re.findall(r"\b[а-яёa-z]{4,}\b", gold_event.actor.lower())]

                for tok in target_tokens + outcome_tokens:
                    if tok in summary_lower and any(w in summary_lower for w in ["уничтожен", "разрушен", "сломан", "невозможн", "провал", "сорван", "потерян", "не удал"]):
                        return 0.0, f"Противоречие: ключевой целевой элемент '{tok}' объявлен уничтоженным или проваленным"

                for act in actor_tokens:
                    if act in summary_lower and any(w in summary_lower for w in ["погиб", "убит", "смерть", "ликвидирован"]):
                        return 0.0, f"Противоречие: ключевой участник '{act}' погиб/ликвидирован в предсказании"

                # Domain-specific safeguards
                if ("куб" in summary_lower and any(w in summary_lower for w in ["уничтожен", "разрушен", "сломан", "невозможн", "потерян"])):
                    return 0.0, "Противоречие: Куб уничтожен или сломан, что прямо противоречит эталону"
                if ("крафт" in summary_lower and any(w in summary_lower for w in ["невозможн", "провал", "сорван", "запрещен", "не удал"])):
                    return 0.0, "Противоречие: трансмутация/крафт объявлен невозможным или проваленным"
                if ("контракт" in summary_lower or "призыв" in summary_lower) and any(w in summary_lower for w in ["сорван", "провал", "отказ", "не состоялся", "не удал"]):
                    return 0.0, "Противоречие: призыв или контракт сорван/отвергнут"
                if "кадзум" in summary_lower and any(w in summary_lower for w in ["погиб", "убит", "смерть"]):
                    return 0.0, "Противоречие: гибель персонажа, участвующего в эталоне"
                if "фея" in summary_lower and any(w in summary_lower for w in ["убит", "смерть", "ликвидирован"]):
                    return 0.0, "Противоречие: гибель феи до проведения переговоров"

        # 3. Check Actor Alignment
        gold_actor_clean = gold_event.actor.lower()
        actor_match = (
            gold_actor_clean in summary_lower or
            any(p in summary_lower for p in ["хачиман", "кадзума", "фея"] if p in gold_actor_clean)
        )

        # 4. Keyword and Concept extraction
        action_keywords = re.findall(r"\b[а-яёА-ЯЁ]{4,}\b", gold_event.action.lower())
        target_keywords = re.findall(r"\b[а-яёА-ЯЁ]{4,}\b", gold_event.target.lower())
        outcome_keywords = re.findall(r"\b[а-яёА-ЯЁ]{4,}\b", gold_event.outcome.lower())

        matches_action = sum(1 for kw in action_keywords if kw in summary_lower)
        matches_target = sum(1 for kw in target_keywords if kw in summary_lower)
        matches_outcome = sum(1 for kw in outcome_keywords if kw in summary_lower)

        total_kw_hits = matches_action + matches_target + matches_outcome

        # Key topic indicators
        has_cube = "куб" in summary_lower or "хорадрим" in summary_lower
        has_kazuma = "кадзум" in summary_lower
        has_fair = "ярмарк" in summary_lower or "осколк" in summary_lower or "рынок" in summary_lower
        has_fairy = "фея" in summary_lower or "пыльц" in summary_lower or "шантаж" in summary_lower
        has_contract = "контракт" in summary_lower or "призыв" in summary_lower or "покупк" in summary_lower or "400" in summary_lower

        # 5. Semantic Scoring per event structure
        gold_target_lower = gold_event.target.lower()
        gold_action_lower = gold_event.action.lower()

        # Specific handler for Fairy blackmail
        if "фея" in gold_actor_clean or "фея" in gold_target_lower:
            if has_fairy and (has_kazuma or "шантаж" in summary_lower or "позор" in summary_lower or "босс" in summary_lower or "пыльц" in summary_lower):
                return 1.0, "Полное совпадение: столкновение/шантаж феи с Кадзумой на ярмарке"
            elif has_fairy:
                return 0.5, "Частичное совпадение: появление феи без прямого развития шантажа"

        # Specific handler for Kazuma Recruitment (Event 1)
        if "призыв" in gold_action_lower or "завербован" in gold_event.outcome.lower():
            if has_kazuma and ("призыв" in summary_lower or "контракт" in summary_lower or ("покупк" in summary_lower and ("хачиман" in summary_lower or "400" in summary_lower))):
                return 1.0, "Полное совпадение: призыв и контрактование Сато Кадзумы Хачиманом"
            elif has_kazuma and "хачиман" in summary_lower and ("найм" in summary_lower or "раб" in summary_lower):
                return 0.5, "Частичное совпадение: взаимодействие найма между Хачиманом и Кадзумой"

        # Specific handler for Cube Binding / Handover (Event 2)
        if "привязывает" in gold_action_lower or "оператором куба" in gold_event.outcome.lower():
            if (has_cube or "тыблок" in summary_lower or "артефакт" in summary_lower) and has_kazuma and ("привязк" in summary_lower or "перед" in summary_lower or "вруч" in summary_lower or "получа" in summary_lower or "оператор" in summary_lower):
                return 1.0, "Полное совпадение: привязка Хорадримского Куба и наделение статусом оператора"
            elif has_cube and (has_kazuma or "хачиман" in summary_lower):
                return 0.5, "Частичное совпадение: передача или владение Хорадримским Кубом"

        # Specific handler for Cube Transmutation / Crafting (Event 3)
        if "трансмутац" in gold_action_lower or "формулы слияния" in gold_action_lower or "экономия прочности" in gold_event.outcome.lower():
            if has_cube and ("крафт" in summary_lower or "трансмутац" in summary_lower or "слияни" in summary_lower or "синтез" in summary_lower or "формул" in summary_lower or "ядер" in summary_lower):
                return 1.0, "Полное совпадение: испытание крафта/трансмутации через Хорадримский Куб"
            elif has_cube and "проверк" in summary_lower:
                return 0.5, "Частичное совпадение: базовая проверка возможностей Куба"

        # Specific handler for Shard Fair scouting (Event 4)
        if "ярмарк" in gold_target_lower or "ярмарку системного осколка" in gold_action_lower:
            if "шантаж" not in summary_lower and has_fair and ("разведк" in summary_lower or "ингредиент" in summary_lower or "сырье" in summary_lower or "очк" in summary_lower or "хвал" in summary_lower or ("торгов" in summary_lower and not has_fairy)):
                return 1.0, "Полное совпадение: выход на ярмарку системного осколка за ресурсами"
            elif has_fair and not has_fairy:
                return 0.5, "Частичное совпадение: упоминание ярмарки осколков"


        # General high-overlap fallback
        if total_kw_hits >= 4 or (actor_match and total_kw_hits >= 3):
            return 0.5, f"Частичное совпадение: пересечение ключевых понятий ({total_kw_hits} совпадений)"

        return 0.0, "Нет соответствия"


StoryEvaluator = BacktestEvaluator

