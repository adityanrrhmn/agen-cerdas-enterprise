# Menjalankan backend (port 8000) dan dashboard (port 5173) di dua jendela PowerShell.
# Pakai: powershell -ExecutionPolicy Bypass -File run-dev.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
