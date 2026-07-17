@echo off
mode con: cols=68 lines=14
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ATENCAO: isso apaga usuarios, planos, QRs e visitas.
set /p ok="Digite APAGAR para confirmar: "
if /I not "%ok%"=="APAGAR" (
  echo Cancelado.
  pause
  exit /b 0
)
if exist "qrcodex.db" del /f /q "qrcodex.db"
if exist "instance\qrcodex.db" del /f /q "instance\qrcodex.db"
echo Banco apagado. Ao rodar o app, ele sera recriado com seed inicial.
pause
