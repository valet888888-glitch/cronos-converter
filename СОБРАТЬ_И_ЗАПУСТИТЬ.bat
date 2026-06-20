@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║    CronosMac v16 — сборка и запуск       ║
echo  ╚══════════════════════════════════════════╝
echo.

echo  [1/3] Установка пакетов...
python -m pip install flask crodump chardet pywebview pyinstaller -q
if errorlevel 1 (
    echo.
    echo  ОШИБКА: Python не найден или нет интернета.
    echo  Установите Python 3.10+ с python.org и повторите.
    pause & exit
)

echo  [2/3] Сборка exe...
if exist dist\cronos_mac rmdir /s /q dist\cronos_mac
if exist build\cronos_mac rmdir /s /q build\cronos_mac

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
    --hidden-import webview ^
    --hidden-import webview.platforms ^
    --hidden-import webview.platforms.winforms ^
    --hidden-import webview.platforms.edgechromium ^
    --collect-all crodump ^
    --collect-all webview ^
    launcher.py --noconfirm >nul 2>&1

if not exist dist\cronos_mac\cronos_mac.exe (
    echo.
    echo  ОШИБКА: exe не создан. Запустите от имени администратора
    echo  или проверьте антивирус (он может блокировать PyInstaller).
    pause & exit
)

echo  [3/3] Запуск...
start "" dist\cronos_mac\cronos_mac.exe

echo.
echo  ════════════════════════════════════════════
echo  Готово! Приложение запущено.
echo.
echo  В следующий раз запускайте напрямую:
echo    dist\cronos_mac\cronos_mac.exe
echo  ════════════════════════════════════════════
echo.
pause
