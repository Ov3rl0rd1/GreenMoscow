# Веб-интерфейс GreenPlan (ASP.NET Core .NET 10)

Тонкий клиент к движку `greenplan`: загрузка чертежа, статус расчёта, итоги, превью и файлы
результата. Вся расчётная логика — в движке; веб только вызывает его HTTP API.

## Состав

| Путь | Что это |
|---|---|
| `src/GreenPlan.Web/Pages/Index` | форма загрузки (.dxf/.dwg/.zip, название, главный чертёж в архиве, YAML настроек) и список расчётов |
| `src/GreenPlan.Web/Pages/Jobs/Details` | статус с автообновлением, итоги, время этапов, превью, файлы |
| `src/GreenPlan.Web/Services/EngineClient` | типизированный `HttpClient` к движку; ошибки сервиса → `EngineRequestException` |
| `src/GreenPlan.Web/Endpoints/ArtifactEndpoints` | прокси файлов результата `/jobs/{id}/artifacts/{name}` |
| `tests/GreenPlan.Web.Tests` | xUnit: клиент на подменном `HttpMessageHandler`, страницы через `WebApplicationFactory`, тест стиля |

## Запуск

Сначала движок (в отдельном окне):

```bash
greenplan serve --port 8000
```

Затем веб:

```bash
dotnet run --project web/src/GreenPlan.Web
```

Интерфейс — `http://localhost:5000`, Swagger движка — `http://localhost:8000/docs`.

## Настройки

`appsettings.json`, секция `Engine` (переопределяется переменными окружения):

| Ключ | Переменная | По умолчанию |
|---|---|---|
| `BaseUrl` | `Engine__BaseUrl` | `http://localhost:8000/` |
| `Timeout` | `Engine__Timeout` | `00:10:00` |
| `MaxUploadBytes` | `Engine__MaxUploadBytes` | 2 ГиБ |

В Docker Compose адрес движка — `http://engine:8000/`.

## Тесты

```bash
dotnet test web/GreenPlan.sln
```

Или вместе с движком: `scripts/test-all.ps1`.

## Правила кода

Комментариев в коде нет — пояснения только в документации; это проверяет
`SourceStyleTests` (Roslyn для `.cs`, поиск `@*` и HTML-комментариев для `.cshtml`).
