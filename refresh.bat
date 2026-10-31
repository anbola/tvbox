@echo off
REM ============================================================
REM  TVBox source refresh - one click
REM  Runs: fetch -> speedtest -> build live -> vod probe -> config -> deploy
REM  Must run on THIS PC (same network as the TV), because speed
REM  ranking is only meaningful from your own broadband.
REM ============================================================
setlocal
cd /d "%~dp0"
title TVBox Refresh

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.x first.
  pause
  exit /b 1
)

set "ARGS=%*"
if "%ARGS%"=="" set "ARGS=--deploy"

echo.
echo  =========================================
echo   TVBox Refresh
echo   python = %PY%
echo   args   = %ARGS%
echo  =========================================
echo.

%PY% tools\refresh_all.py %ARGS%
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo  [OK] Done. Check the App: clear config cache, re-load config address.
) else (
  echo  [FAIL] Exit code %RC% - see log above.
)
echo.
pause
exit /b %RC%
