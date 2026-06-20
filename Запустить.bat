@echo off
cd /d "%~dp0"

:: Try py launcher (most reliable on Windows)
py --version >nul 2>&1
if not errorlevel 1 (
    echo Installing packages...
    py -m pip install flask crodump chardet pywebview -q
    for /f "delims=" %%i in ('py -c "import sys,os; print(os.path.dirname(sys.executable))"') do set PYDIR=%%i
    goto :start
)

:: Try python command
python --version >nul 2>&1
if not errorlevel 1 (
    echo Installing packages...
    python -m pip install flask crodump chardet pywebview -q
    for /f "delims=" %%i in ('python -c "import sys,os; print(os.path.dirname(sys.executable))"') do set PYDIR=%%i
    goto :start
)

echo Python not found! Install Python 3.10+ from python.org
pause
exit

:start
echo Starting CronosMac v16...
start "" "%PYDIR%\pythonw.exe" "%~dp0launcher.py"
exit
