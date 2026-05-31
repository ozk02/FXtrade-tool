@echo off
rem ============================================================
rem  FX jido baibai - demo trade UI launcher (Windows)
rem  Double-click, or use the desktop shortcut, to start.
rem ============================================================
cd /d "%~dp0"
title FX Demo Trade
echo Starting FX demo trade UI...
echo (A browser will open at http://localhost:8000)
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py -m fxtrade ui
) else (
    python -m fxtrade ui
)

echo.
echo Server stopped. Press any key to close this window.
pause >nul
