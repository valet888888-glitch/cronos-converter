"""
CronosMac — нативное окно через pywebview.
Flask запускается в фоновом потоке, pywebview показывает интерфейс.
Никакого браузера, никакого терминала.
"""
import sys
import os
import threading
import time
import urllib.request

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

from app import app as flask_app

PORT = 5055


def _run_flask():
    flask_app.run(host='127.0.0.1', port=PORT, debug=False,
                  use_reloader=False, threaded=True)


class _Api:
    """JS API: вызывается из JavaScript через window.pywebview.api.*"""

    def __init__(self):
        self.window = None

    def browse_folder(self):
        """Показывает диалог выбора папки, возвращает путь или ''."""
        if not self.window:
            return ''
        import webview
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            return result[0]
        return ''

    def open_folder(self, path):
        """Открывает папку в проводнике / Finder."""
        if not path or not os.path.isdir(path):
            return False
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', path])
        else:
            import subprocess
            subprocess.Popen(['xdg-open', path])
        return True


def _wait_flask(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=0.5)
            return
        except Exception:
            time.sleep(0.1)


def main():
    t = threading.Thread(target=_run_flask, daemon=True)
    t.start()
    _wait_flask(PORT)

    import webview

    api = _Api()
    window = webview.create_window(
        title='CronosMac — Конвертер баз данных',
        url=f'http://127.0.0.1:{PORT}',
        width=1100,
        height=750,
        resizable=True,
        min_size=(800, 500),
        js_api=api,
    )
    api.window = window
    webview.start()


if __name__ == '__main__':
    main()
