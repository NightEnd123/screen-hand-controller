# One-time developer setup: Python 3.12 venv, packages, hand-tracking model.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.12 -m venv .venv }
    else { python -m venv .venv }
}
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Force models | Out-Null
if (-not (Test-Path models\hand_landmarker.task)) {
    Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task" -OutFile models\hand_landmarker.task
}
Write-Host "Done. Start with run.bat (with the debug view) or run_hidden.vbs (background)."
