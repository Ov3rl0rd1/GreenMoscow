param(
    [int]$EnginePort = 8000,
    [int]$WebPort = 8080,
    [int]$TimeoutSeconds = 600,
    [switch]$KeepRunning
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$engineUrl = "http://localhost:$EnginePort"
$webUrl = "http://localhost:$WebPort"
$workDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "greenplan-smoke-$(Get-Random)"

function Wait-Until([scriptblock]$Probe, [string]$What, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $result = & $Probe
            if ($result) { return $result }
        } catch { }
        Start-Sleep -Seconds 3
    }
    throw "Не дождались: $What"
}

function New-SampleDrawing([string]$Path) {
    if (-not (Test-Path $python)) { throw "Нужен .venv для подготовки тестового чертежа: $python" }
    $script = @"
import sys
from pathlib import Path
sys.path.insert(0, r'$repositoryRoot\engine\tests')
from fixtures.export_pipeline import source_drawing
source_drawing(Path(r'$Path'))
"@
    $script | & $python -
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось подготовить тестовый чертёж' }
}

New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
$drawing = Join-Path $workDirectory 'street.dxf'

try {
    Push-Location $repositoryRoot
    docker compose up --build --detach
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up завершился с ошибкой' }

    Wait-Until { (Invoke-RestMethod "$engineUrl/healthz" -TimeoutSec 5).status -eq 'ok' } 'движок ответит на /healthz' $TimeoutSeconds
    Write-Output 'Движок готов'

    New-SampleDrawing $drawing
    $created = Invoke-RestMethod -Uri "$engineUrl/api/v1/jobs" -Method Post -Form @{
        drawing = Get-Item -LiteralPath $drawing
        title   = 'Смоук-тест'
    }
    Write-Output "Задание: $($created.job_id)"

    $job = Wait-Until {
        $current = Invoke-RestMethod "$engineUrl/api/v1/jobs/$($created.job_id)" -TimeoutSec 10
        if ($current.status -in @('succeeded', 'failed')) { $current } else { $null }
    } 'расчёт завершится' $TimeoutSeconds

    if ($job.status -ne 'succeeded') { throw "Расчёт не удался: $($job.error)" }
    if (-not $job.summary.verification_valid) { throw 'Независимая проверка не пройдена' }
    Write-Output "Деревьев: $($job.summary.trees), кустарников: $($job.summary.shrubs), проверка пройдена"

    $preview = Invoke-WebRequest "$engineUrl/api/v1/jobs/$($created.job_id)/artifacts/preview.png" -TimeoutSec 30
    if ($preview.RawContentLength -le 0) { throw 'Пустое превью' }

    $page = Wait-Until {
        $response = Invoke-WebRequest $webUrl -TimeoutSec 10
        if ($response.StatusCode -eq 200) { $response } else { $null }
    } 'веб-интерфейс ответит' $TimeoutSeconds
    if ($page.Content -notmatch 'GreenMoscow') { throw 'Веб-интерфейс вернул неожиданную страницу' }

    Write-Output 'Docker-смоук пройден: движок, расчёт, артефакты и веб-интерфейс работают'
} finally {
    if (-not $KeepRunning) {
        docker compose down --volumes | Out-Null
    }
    Pop-Location
    Remove-Item -LiteralPath $workDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
