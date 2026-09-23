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
greenplan-ml evaluate      --dataset <каталог> --model <модель.onnx> --output <отчёты>
```

## Тесты

```powershell
cd ml
..\.venv\Scripts\python.exe -m pytest -m "not realdata"
```

Тесты на реальных данных требуют распакованного датасета в `data/pilot/` и `dwg2dxf`.
