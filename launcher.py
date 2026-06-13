"""
Точка входа для Windows .exe (--onedir режим PyInstaller)

Структура после сборки:
  cronos_mac\
    cronos_mac.exe        <- запускать
    _internal\            <- sys._MEIPASS = здесь web/, core/, dll-ки
    data\                 <- создаётся автоматически, тут cronos_mac.db
"""
import sys
import os
import threading
import webbrowser
import time

if getattr(sys, 'frozen', False):
    # exe-папка: рядом с cronos_mac.exe
    _exe_dir = os.path.dirname(sys.executable)
    os.chdir(_exe_dir)

from app import app

PORT = 5055
URL = f"http://localhost:{PORT}"


def _open_browser():
    time.sleep(1.5)
    webbrowser.open(URL)


if __name__ == '__main__':
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)
