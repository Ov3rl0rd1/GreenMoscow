import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

import docx
import yaml

LEVEL_TITLES = (
    ("Основной ассортимент деревьев", "main"),
    ("Дополнительный ассортимент деревьев", "additional"),
    ("Ассортимент перспективных видов", "perspective"),
)
GROUPS = {
    "Хвойные деревья": "conifer_tree",
    "Хвойные кустарники": "conifer_shrub",
    "Лиственные деревья": "deciduous_tree",
    "Лиственные кустарники": "deciduous_shrub",
    "Лианы": "liana",
}
COLUMNS = (
    ("yards", "1", "Дворовые территории", "дворовые территории"),
    ("preschool", "2", "Дошкольные учреждения", "дошкольные учреждения"),
    (
        "schools_sport",
        "3",
        "Общеобразовательные и спортивные учреждения (школы, колледжи)",
        "школы, колледжи и спортивные учреждения",
    ),
    (
        "healthcare",
        "4",
        "Учреждения здравоохранения и реабилитационные центры",
        "учреждения здравоохранения",
    ),
    (
        "roads",
        "5",
        "Магистрали (шоссе, проспекты, улицы с высокоскоростным движением, кольцевые дороги и хорды), "
        "*внутриквартальные улицы и проезды местного значения",
        "магистрали и внутриквартальные улицы",
    ),
    (
        "public_spaces",
        "6",
        "Площади, пространства общественно-делового и торгово-развлекательного назначения",
        "площади и общественные пространства",
    ),
    (
        "parks",
        "7",
        "Парки, *бульвары, скверы, набережные, сады",
        "парки, бульвары, скверы, набережные",
    ),
    (
        "industrial",
        "8",
        "Территории производственного назначения, *озеленённые территории охранных и санитарно-защитных зон",
        "производственные и санитарно-защитные территории",
    ),
)
VERDICTS = {"+", "-"}
LEADING_CELLS = 2
NOTE_ROW = re.compile(r"^\[(\d+)\]\s*-\s*(.+)$")
NOTE_MARK = re.compile(r"\[(\d+)\]")
SPACE_BEFORE_BRACKET = re.compile(r"\s*\(")
LOOSE_COMMAS = re.compile(r"(\s*,)+\s*(?=\(|$)")
FOOTNOTE_STARTS = ("1 На территориях", "На территориях", "*Обозначенный")


@dataclass
class TableState:
    level: str = ""
    group: str = ""
    irregular: list[str] = field(default_factory=list)


def cell_texts(row) -> list[str]:
    return [" ".join(cell.xpath("string(.)").split()) for cell in row._tr.tc_lst]


def is_banner(cells: list[str]) -> bool:
    return len(set(cells)) == 1


def is_species_row(cells: list[str]) -> bool:
    return len(cells) > LEADING_CELLS and cells[0].isdigit() and not cells[1].isdigit()


def species_record(cells: list[str], state: TableState) -> dict:
    source_name = cells[1]
    verdicts = cells[LEADING_CELLS:]
    if len(verdicts) != len(COLUMNS) or any(value not in VERDICTS for value in verdicts):
        state.irregular.append(f"{source_name}: {verdicts}")
    return {
        "name_ru": clean_name(source_name),
        "source_name": source_name,
        "level": state.level,
        "group": state.group,
        "notes": sorted({int(number) for number in NOTE_MARK.findall(source_name)}),
        "columns": {
            column_id: verdicts[index] if index < len(verdicts) and verdicts[index] in VERDICTS else None
            for index, (column_id, _, _, _) in enumerate(COLUMNS)
        },
    }


def clean_name(source_name: str) -> str:
    without_marks = NOTE_MARK.sub(" ", source_name)
    spaced = SPACE_BEFORE_BRACKET.sub(" (", without_marks)
    return LOOSE_COMMAS.sub(" ", " ".join(spaced.split())).strip(", ")


def parse_document(path: Path, notes: dict[int, str], footnotes: list[str], irregular: list[str]) -> list[dict]:
    table = docx.Document(str(path)).tables[0]
    state = TableState(irregular=irregular)
    records: list[dict] = []
    for row in table.rows:
        cells = cell_texts(row)
        if is_banner(cells):
            absorb_banner(cells[0], state, notes, footnotes)
        elif is_species_row(cells):
            records.append(species_record(cells, state))
    return records


def absorb_banner(text: str, state: TableState, notes: dict[int, str], footnotes: list[str]) -> None:
    level = next((code for title, code in LEVEL_TITLES if text.startswith(title)), None)
    note = NOTE_ROW.match(text)
    if level is not None:
        state.level = level
    elif text in GROUPS:
        state.group = GROUPS[text]
    elif note is not None:
        notes.setdefault(int(note.group(1)), note.group(2).strip())
    elif text.startswith(FOOTNOTE_STARTS) and text not in footnotes:
        footnotes.append(text.removeprefix("1 "))


def build(sources: list[Path], output: Path) -> None:
    notes: dict[int, str] = {}
    footnotes: list[str] = []
    irregular: list[str] = []
    species = [record for path in sources for record in parse_document(path, notes, footnotes, irregular)]
    document = {
        "meta": {
            "title_ru": "Ассортимент деревьев, кустарников и лиан для озеленения различных категорий "
            "территорий города Москвы (основной, дополнительный, перспективный)",
            "publisher_ru": "ДПиООС города Москвы, mos.ru",
            "received": "2026-09-23",
            "sources": [f"research/raw/assortment/{path.name}" for path in sources],
            "species_count": len(species),
        },
        "columns": [
            {"id": column_id, "number": int(number), "name_ru": name, "short_ru": short}
            for column_id, number, name, short in COLUMNS
        ],
        "notes": {number: notes[number] for number in sorted(notes)},
        "footnotes_ru": footnotes,
        "species": species,
    }
    output.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    print(f"{output}: {len(species)} видов, примечаний {len(notes)}")
    for line in irregular:
        print(f"нестандартная строка: {line}")


def main() -> None:
    parser = argparse.ArgumentParser(description="таблицы ассортимента ДПиООС из docx в YAML")
    parser.add_argument("--sources", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build(arguments.sources, arguments.output)


if __name__ == "__main__":
    main()
