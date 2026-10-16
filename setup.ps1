$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Không tạo được .venv. Hãy cài Python 3.11–3.13.' }
}
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
function Invoke-ProjectPython {
    & $taskPython @args
    if ($LASTEXITCODE -ne 0) { throw "Bước triển khai thất bại: $args" }
}
Invoke-ProjectPython -m pip install -e .
Invoke-ProjectPython scripts/download_model.py
Invoke-ProjectPython scripts/download_data.py --full
Invoke-ProjectPython scripts/train_model.py
Invoke-ProjectPython scripts/evaluate_demo.py
Write-Host 'Sẵn sàng. Chạy .\run.ps1 rồi mở http://127.0.0.1:8000' -ForegroundColor Green
