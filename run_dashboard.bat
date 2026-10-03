@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing/checking dependencies...
pip install -r requirements.txt -q

if not exist .env (
    echo No .env found - copying .env.example.
    copy .env.example .env >nul
)

start "MUSFIRA AI Backend" cmd /k "python app.py"

echo.
echo Waiting for the server to come online...
set RETRIES=0

:waitloop
set /a RETRIES+=1
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:5000/api/health -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 goto ready
if %RETRIES% GEQ 30 goto failed
timeout /t 1 /nobreak >nul
goto waitloop

:ready
start "" "http://127.0.0.1:5000/"
echo.
echo MUSFIRA AI Support running at http://127.0.0.1:5000
echo (Settings and Dashboard are tabs inside that same page now)
echo.
echo This launcher window will close on its own in 5 seconds.
echo IMPORTANT: a separate "MUSFIRA AI Backend" window is your actual
echo running server - keep THAT one open. Closing it stops the bot.
timeout /t 5 /nobreak >nul
exit /b 0

:failed
echo.
echo ============================================================
echo The server did NOT respond within 30 seconds.
echo Look at the "MUSFIRA AI Backend" window that opened - it will
echo show the real error (common causes: a dependency failed to
echo install, or another program is already using port 5000).
echo ============================================================
pause
endlocal
