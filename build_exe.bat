@echo off
REM Сборка sql_to_cronos.exe
REM Требует: pip install pyinstaller

echo Проверка PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Устанавливаю PyInstaller...
    pip install pyinstaller
)

echo.
echo Сборка exe...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "sql_to_cronos" ^
    --icon NONE ^
    sql_to_cronos.py

echo.
if exist dist\sql_to_cronos.exe (
    echo Готово: dist\sql_to_cronos.exe
    dir dist\sql_to_cronos.exe
) else (
    echo ОШИБКА: exe не создан
)
pause
