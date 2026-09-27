from dataclasses import replace

from greenplan.domain.norms import SHRUB
from greenplan.explain.explanation_model import ElementView, PlantExplanation
from greenplan.explain.text_renderer import element_sentence, rows_word


def shrub_in(element: ElementView) -> PlantExplanation:
    return PlantExplanation(
        plant_id="S-0001",
        status="accepted",
        plant_type=SHRUB,
        x=0.0,
        y=0.0,
        crown_diameter_m=1.5,
        species=None,
        clearances=(),
        violations=(),
        explanation_ru="",
        element=element,
    )


def test_band_sentence_names_its_rows() -> None:
    band = ElementView("shrub-hedge-001", "hedge", "живая изгородь", 172, 1.02, "вдоль проезжей части", "", 3)
    sentence = element_sentence(shrub_in(band))
    assert "172 шт. в 3 ряда, шаг 1.02 м" in sentence or "172 шт. в 3 ряда, шаг 1,02 м" in sentence
    single = element_sentence(shrub_in(replace(band, rows=1)))
    assert "ряд" not in single


def test_rows_word_agrees_with_the_number() -> None:
    assert [rows_word(count) for count in (2, 3, 5, 12, 22)] == ["ряда", "ряда", "рядов", "рядов", "ряда"]
