param(
    [switch]$IncludeRealData,
    [switch]$SkipWeb
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$markerExpression = if ($IncludeRealData) { '' } else { 'not realdata' }
$failures = @()

function Invoke-PythonTests([string]$projectDirectory) {
    if (-not (Test-Path (Join-Path $projectDirectory 'tests'))) { return }
    Push-Location $projectDirectory
    try {
        if ($markerExpression) { & $python -m pytest -m $markerExpression } else { & $python -m pytest }
        if ($LASTEXITCODE -ne 0) { $script:failures += $projectDirectory }
    } finally { Pop-Location }
}

Invoke-PythonTests (Join-Path $repositoryRoot 'engine')
Invoke-PythonTests (Join-Path $repositoryRoot 'ml')

$solution = Join-Path $repositoryRoot 'web\GreenPlan.sln'
if (-not $SkipWeb -and (Test-Path $solution)) {
    dotnet test $solution
    if ($LASTEXITCODE -ne 0) { $failures += 'web' }
}

if ($failures.Count -gt 0) {
    Write-Error ("Failed test suites: " + ($failures -join ', '))
}
Write-Output 'All test suites passed'
