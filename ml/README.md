# `greenplan-ml` — модель подсказок размещения

Пакет обучает и применяет модель, которая предлагает места посадок. Она **необязательна**:
движок без неё выдаёт полный результат, а флаг `--no-ml` отключает её принудительно.
Нормы проверяет движок — модель только меняет порядок предпочтения клеток.

| Документ | О чём |
|---|---|
| [TRAINING.md](TRAINING.md) | сборка примеров, профили обучения, экспорт в ONNX, применение в движке |
| [EVALUATION.md](EVALUATION.md) | как меряется качество и как сравнение с правилами устроено |
| [EXTERNAL_DATASETS.md](EXTERNAL_DATASETS.md) | какие внешние источники рассматривались и почему не подошли |

## Установка

```powershell
.\.venv\Scripts\python.exe -m pip install -e engine
.\.venv\Scripts\python.exe -m pip install -e ml[dev]
```

## Команды

```
greenplan-ml build-dataset --dataset-root <датасет> --output <каталог> [--levels A]
greenplan-ml train         --dataset <каталог> --output <прогон> [--profile rtx3050]
greenplan-ml export        --checkpoint <прогон>/model.pt --output <модель.onnx>
greenplan-ml calibrate     --dataset <каталог> --model <модель.onnx> --objects <id ...> --output <модель.onnx>
greenplan-ml evaluate      --dataset <каталог> --model <модель.onnx> --output <отчёты>
greenplan-ml similarity    --dataset <каталог> --runs имя=<прогон batch> ... --output <отчёты>
greenplan-ml figures       --dataset <каталог> --runs "Заголовок=<прогон batch>" ... --output <картинки>
greenplan-ml audit-reference --dataset-root <датасет> --output <отчёты> [--only <id ...>]
```

`similarity` сравнивает итоговые планы движка после всех норм с проектными решениями, `figures`
рисует эталон рядом с планами, `audit-reference` проверяет сами проектные решения теми же нормами.
Результаты на датасете — в корневом README и в TRAINING.md (шаги 6–7).

## Тесты

```powershell
cd ml
..\.venv\Scripts\python.exe -m pytest -m "not realdata"
```

Тесты на реальных данных требуют распакованного датасета в `data/pilot/` и `dwg2dxf`.
