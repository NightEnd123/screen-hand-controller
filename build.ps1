# Build the downloadable app: dist\GestureControl\GestureControl.exe and a zip of that folder.
# Needs the dev setup first (setup.ps1). Usage:  .\build.ps1 [-Version 0.1.0]
param([string]$Version = "dev")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --quiet "pyinstaller==6.16.0"
if (-not (Test-Path models\hand_landmarker.task)) { throw "models\hand_landmarker.task missing: run setup.ps1 first" }
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "tests failed" }
& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\GestureControl.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Copy-Item README.md dist\GestureControl\README.md
$zip = "dist\GestureControl-$Version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\GestureControl -DestinationPath $zip
Write-Host "Built $zip"
