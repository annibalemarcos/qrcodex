@echo off
mode con: cols=68 lines=14
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo ================================================
echo   QRCodex - instalar + rodar
echo ================================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado no PATH.
  echo Instale o Python 3.10+ e marque "Add Python to PATH".
  pause
  exit /b 1
)
if not exist ".venv" (
  echo Criando ambiente virtual...
  python -m venv .venv
  if errorlevel 1 (
    echo Falha ao criar ambiente virtual.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 (
  echo Falha ao atualizar pip.
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Instalacao falhou. Veja o erro acima.
  pause
  exit /b 1
)
if not exist ".env" copy .env.example .env >nul
set FLASK_PORT=5432
start "" "http://localhost:5432"
python app.py
pause
