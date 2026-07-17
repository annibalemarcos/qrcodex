@echo off
mode con: cols=68 lines=14
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo ================================================
echo   QRCodex - rodando na porta 5432
echo ================================================
echo.
if not exist ".venv\Scripts\activate.bat" (
  echo Ambiente virtual nao encontrado. Rode instalar.bat primeiro.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
set FLASK_PORT=5432
start "" "http://localhost:5432"
python app.py
pause
