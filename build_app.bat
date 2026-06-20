@echo off
REM ============================================================
REM  Сборка CronosMac.exe v13 — браузер + tkinter-окно управления
REM  Требует: pip install pyinstaller flask crodump chardet
REM  tkinter встроен в Python — отдельно не нужен
REM ============================================================

echo Установка зависимостей...
python -m pip install pyinstaller flask crodump chardet >nul 2>&1

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
    --hidden-import crodump.koddecoder ^
    --hidden-import werkzeug ^
    --hidden-import werkzeug.serving ^
    --hidden-import werkzeug.routing ^
    --hidden-import werkzeug.middleware ^
    --hidden-import werkzeug.middleware.shared_data ^
    --hidden-import click ^
    --hidden-import itsdangerous ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --collect-all crodump ^
    launcher.py

echo.
if exist dist\cronos_mac\cronos_mac.exe (
    echo ================================================
    echo  Готово: dist\cronos_mac\
    echo  Запуск: cronos_mac.exe
    echo  Откроет браузер автоматически.
    echo ================================================
) else (
    echo ОШИБКА: exe не создан
)
pause
