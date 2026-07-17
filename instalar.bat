@echo off
mode con: cols=68 lines=14
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo ================================================
echo   QRCodex - instalador
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
  echo Dica: use Python 3.10, 3.11, 3.12, 3.13 ou 3.14.
  pause
  exit /b 1
)
if not exist ".env" (
  copy .env.example .env >nul
  echo Arquivo .env criado a partir do exemplo.
)
echo.
echo Instalacao finalizada com sucesso.
pause
