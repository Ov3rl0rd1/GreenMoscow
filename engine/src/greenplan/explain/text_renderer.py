from collections.abc import Sequence

from greenplan.domain.decisions import REJECTED
from greenplan.domain.norms import ADVISORY, CONDITIONAL_MEASURE, PROHIBITIVE, ROOT_BARRIER_RULE_SUFFIX
from greenplan.explain.explanation_model import (
    CitationView,
    ClearanceView,
    PlantExplanation,
    SpeciesView,
    ViolationView,
)
from greenplan.explain.number_format import format_number
from greenplan.knowledge.explanation_terms import ExplanationTerms


class ExplanationTextRenderer:
    def __init__(self, terms: ExplanationTerms) -> None:
        self._terms = terms

    def render(self, plant: PlantExplanation) -> str:
        sentences = [self._headline(plant)]
        sentences.extend(self._violation_sentence(violation) for violation in plant.violations)
        sentences.extend(
            self._clearance_sentence(clearance, plant.crown_diameter_m) for clearance in plant.clearances
        )
        sentences.append(_root_barrier_sentence(plant))
        if plant.species is not None:
            sentences.extend(self._species_sentences(plant.species))
        return " ".join(sentence for sentence in sentences if sentence)

    def _headline(self, plant: PlantExplanation) -> str:
        target = self._terms.target(plant.plant_type).genitive_ru
        status = self._terms.status(plant.status)
        if plant.status == REJECTED:
            return f"Посадка {target} в данной точке {status}."
        return f"Посадка {target} {status}."

    def _violation_sentence(self, violation: ViolationView) -> str:
        text = _capitalized(violation.text_ru)
        cite = _cite(violation.citations)
        if violation.actual_m is None or violation.required_m is None:
            return f"{text}{cite}."
        numbers = (
            f"{format_number(violation.actual_m)} м при минимуме {format_number(violation.required_m)} м"
        )
        return f"{text}: {numbers}{cite}."

    def _clearance_sentence(self, clearance: ClearanceView, crown_diameter_m: float) -> str:
        obstacle = self._terms.obstacle(clearance.obstacle_kind)
        cite = _cite(clearance.citations)
        distance = f"{format_number(clearance.actual_m)} м"
        required = f"{format_number(clearance.required_m)} м"
        if clearance.satisfied:
            core = (
                f"Расстояние {obstacle.from_ru} {clearance.measurement_ru} — {distance} "
                f"при требуемых {required}{cite}."
            )
        elif clearance.severity == PROHIBITIVE:
            deficit = format_number(abs(clearance.margin_m))
            core = (
                f"Нарушено: расстояние {obstacle.from_ru} {clearance.measurement_ru} — {distance} "
                f"при требуемых {required}, дефицит {deficit} м{cite}."
            ) + _barrier_minimum_note(clearance)
        elif clearance.severity == CONDITIONAL_MEASURE:
            core = (
                f"Расстояние {obstacle.from_ru} {clearance.measurement_ru} — {distance}, меньше нормы "
                f"{required}: посадка допустима только при условии — {clearance.condition_ru}{cite}."
            )
        elif clearance.severity == ADVISORY:
            core = (
                f"Рекомендация не выполнена: расстояние {obstacle.from_ru} — {distance} "
                f"при рекомендуемых {required}{cite}."
            )
        else:
            condition = f"; {clearance.condition_ru}" if clearance.condition_ru else ""
            core = f"Точка в {obstacle.zone_ru}: {distance} при ширине зоны {required}{condition}{cite}."
        return core + self._crown_note(clearance, crown_diameter_m) + _radius_note(clearance)

    def _crown_note(self, clearance: ClearanceView, crown_diameter_m: float) -> str:
        if clearance.crown_increment_m <= 0:
            return ""
        return (
            f" Норма {format_number(clearance.base_required_m)} м увеличена на "
            f"{format_number(clearance.crown_increment_m)} м для кроны {format_number(crown_diameter_m)} м "
            f"— допущение решения{_cite(clearance.crown_rule_citations)}."
        )

    def _species_sentences(self, species: SpeciesView) -> list[str]:
        sentences = [f"Порода: {species.name_ru}."]
        sentences.extend(
            f"Основание выбора породы: {_lowercased(reason.text_ru.rstrip('.'))}{_cite(reason.citations)}."
            for reason in species.reasons
        )
        if species.alternatives:
            listed = "; ".join(f"{item.name_ru} — {item.reason_ru}" for item in species.alternatives)
            sentences.append(f"Рассмотрены также: {listed}.")
        sentences.append(f"{_capitalized(species.invasive_text_ru)}{_cite(species.invasive_citations)}.")
        return sentences


def _radius_note(clearance: ClearanceView) -> str:
    if not clearance.assumed_outer_radius:
        return ""
    return " Диаметр сети на подоснове не подписан — принят консервативный по умолчанию (допущение решения)."


def _barrier_minimum_note(clearance: ClearanceView) -> str:
    if not clearance.rule_id.endswith(ROOT_BARRIER_RULE_SUFFIX):
        return ""
    return " Это наименьшее допустимое расстояние даже при устройстве корнезащиты."


def _root_barrier_sentence(plant: PlantExplanation) -> str:
    if plant.root_barrier_length_m <= 0:
        return ""
    return f"Корнезащита вдоль сети: {format_number(plant.root_barrier_length_m)} м."


def _cite(citations: Sequence[CitationView]) -> str:
    return f" ({'; '.join(citation.text_ru for citation in citations)})" if citations else ""


def _capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


def _lowercased(text: str) -> str:
    return text[:1].lower() + text[1:]
