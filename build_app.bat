@echo off
REM ============================================================
REM  Сборка CronosMac  (папка cronos_mac\ + cronos_mac.exe)
REM  Требует: pip install pyinstaller flask cronodump chardet
REM ============================================================

echo Проверка PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Устанавливаю PyInstaller...
    pip install pyinstaller
)

REM Очищаем предыдущую сборку
if exist dist\cronos_mac rmdir /s /q dist\cronos_mac
if exist build\cronos_mac rmdir /s /q build\cronos_mac

echo.
echo Сборка...

python -m PyInstaller ^
    --onedir ^
    --console ^
    --name "cronos_mac" ^
    --add-data "web;web" ^
    --add-data "core;core" ^
    --hidden-import flask ^
    --hidden-import flask.templating ^
    --hidden-import jinja2 ^
    --hidden-import jinja2.ext ^
    --hidden-import chardet ^
    --hidden-import crodump ^
    --hidden-import crodump.crofile ^
    --hidden-import crodump.crodump ^
    --hidden-import crodump.crobankfile ^
    --hidden-import werkzeug ^
    --hidden-import werkzeug.serving ^
    --hidden-import werkzeug.routing ^
    --hidden-import werkzeug.middleware ^
    --hidden-import werkzeug.middleware.shared_data ^
    --hidden-import click ^
    --hidden-import itsdangerous ^
    --collect-all crodump ^
    launcher.py

echo.
if exist dist\cronos_mac\cronos_mac.exe (
    echo.
    echo ================================================
    echo  Готово!  Папка: dist\cronos_mac\
    echo.
    echo  Структура:
    echo    dist\cronos_mac\
    echo      cronos_mac.exe    ^<-- запускать этот файл
    echo      _internal\        ^<-- не трогать
    echo      data\             ^<-- создастся при первом запуске
    echo.
    echo  Для переноса: скопируйте всю папку cronos_mac\
    echo ================================================
) else (
    echo ОШИБКА: exe не создан, проверьте вывод выше
)
pause
