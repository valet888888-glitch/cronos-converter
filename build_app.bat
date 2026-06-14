@echo off
REM ============================================================
REM  Сборка CronosMac.exe — нативное окно, без браузера и терминала
REM  Требует: pip install pyinstaller flask cronodump chardet pywebview
REM ============================================================

echo Установка зависимостей...
pip install pyinstaller flask cronodump chardet pywebview >nul 2>&1

if exist dist\cronos_mac rmdir /s /q dist\cronos_mac
if exist build\cronos_mac rmdir /s /q build\cronos_mac

echo Сборка...

python -m PyInstaller ^
    --onedir ^
    --windowed ^
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
    --hidden-import webview ^
    --hidden-import webview.platforms ^
    --hidden-import webview.platforms.winforms ^
    --collect-all crodump ^
    --collect-all webview ^
    launcher.py

echo.
if exist dist\cronos_mac\cronos_mac.exe (
    echo ================================================
    echo  Готово: dist\cronos_mac\
    echo  Запуск: cronos_mac.exe
    echo  Без браузера. Без терминала. Без Python.
    echo ================================================
) else (
    echo ОШИБКА: exe не создан
)
pause
