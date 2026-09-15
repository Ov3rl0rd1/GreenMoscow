$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$targetDirectory = Join-Path $repositoryRoot 'tools\bin\libredwg'
$releases = Invoke-RestMethod -Uri 'https://api.github.com/repos/LibreDWG/libredwg/releases?per_page=5' -UserAgent 'greenplan'
$asset = $releases | ForEach-Object { $_.assets } | Where-Object { $_.name -match 'win64.*\.zip$' } | Select-Object -First 1
if (-not $asset) { throw 'LibreDWG win64 release asset not found' }
$archive = Join-Path $env:TEMP $asset.name
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archive -UserAgent 'greenplan'
New-Item -ItemType Directory -Force $targetDirectory | Out-Null
Expand-Archive -Path $archive -DestinationPath $targetDirectory -Force
Get-ChildItem $targetDirectory -Recurse -Filter 'dwg2dxf.exe' | Select-Object -First 1 -ExpandProperty FullName
