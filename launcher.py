"""
CronosMac — нативное окно через pywebview.
Flask запускается в фоновом потоке, pywebview показывает интерфейс.
Никакого браузера, никакого терминала.
"""
import sys
import os
import threading
import time

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

from app import app as flask_app

PORT = 5055


def _run_flask():
    flask_app.run(host='127.0.0.1', port=PORT, debug=False,
                  use_reloader=False, threaded=True)


def main():
    t = threading.Thread(target=_run_flask, daemon=True)
    t.start()
    # Ждём пока Flask поднимется
    time.sleep(1.2)

    import webview
    window = webview.create_window(
        title='CronosMac — Конвертер баз данных',
        url=f'http://127.0.0.1:{PORT}',
        width=1100,
        height=750,
        resizable=True,
        min_size=(800, 500),
    )
    webview.start()


if __name__ == '__main__':
    main()
