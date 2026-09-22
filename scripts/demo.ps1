#Requires -Version 5.1
param(
    [string]$ObjectId = "bagritskogo",
    [string]$DatasetRoot = "data/pilot/Пилотный проект 20 улиц",
    [string]$Output = "data/demo",
    [string]$Territory = "district_street",
    [string]$Model = ""
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repositoryRoot

$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Не найден .venv: $python" }

$objects = Join-Path $repositoryRoot 'knowledge\dataset\pilot_objects.yaml'
$catalog = Get-Content -LiteralPath $objects -Raw -Encoding UTF8
if ($catalog -notmatch "id:\s*$ObjectId") { throw "Объект '$ObjectId' не найден в $objects" }

$outputDirectory = Join-Path $repositoryRoot $Output
$converter = Join-Path $repositoryRoot 'tools\bin\libredwg\dwg2dxf.exe'
$arguments = @(
    '-m', 'greenplan.cli.main', 'batch',
    '--dataset-root', (Join-Path $repositoryRoot $DatasetRoot),
    '--output', $outputDirectory,
    '--only', $ObjectId,
    '--territory', $Territory
)
if (Test-Path $converter) { $arguments += @('--dwg2dxf', $converter, '--cache', (Join-Path $repositoryRoot 'data\cache\converted')) }
if ($Model) { $arguments += @('--model', (Join-Path $repositoryRoot $Model)) }

$env:PYTHONIOENCODING = 'utf-8'
Write-Output "Расчёт объекта $ObjectId (категория $Territory)…"
& $python @arguments
if ($LASTEXITCODE -gt 1) { throw "Расчёт завершился с кодом $LASTEXITCODE" }

$objectDirectory = Join-Path $outputDirectory $ObjectId
$preview = Join-Path $objectDirectory 'preview.png'
$report = Join-Path $objectDirectory 'planting_report.md'
$verification = Join-Path $objectDirectory 'verification_report.md'

Write-Output ''
Write-Output "Результаты: $objectDirectory"
Get-ChildItem -LiteralPath $objectDirectory | Select-Object Name, Length | Format-Table | Out-String | Write-Output

foreach ($path in @($preview, $report, $verification)) {
    if (Test-Path -LiteralPath $path) { Start-Process -FilePath $path }
}
