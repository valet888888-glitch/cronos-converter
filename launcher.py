import sys, os, threading, time, urllib.request, logging, subprocess, traceback

# Hide console immediately
if sys.platform == 'win32':
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

# Redirect stdout/stderr when frozen (windowed exe)
if getattr(sys, 'frozen', False):
    import io
    if sys.stdout is None: sys.stdout = io.StringIO()
    if sys.stderr is None: sys.stderr = io.StringIO()
    os.chdir(os.path.dirname(sys.executable))

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('flask').setLevel(logging.ERROR)


def _msgbox(title, msg):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, str(msg), str(title), 0x10)
    except Exception:
        pass


# Load Flask app — show error dialog if anything fails
try:
    from app import app as flask_app
except Exception as e:
    _msgbox('CronosMac - Load Error', traceback.format_exc())
    sys.exit(1)

PORT = 5055


def _run_flask():
    try:
        flask_app.run(host='127.0.0.1', port=PORT, debug=False,
                      use_reloader=False, threaded=True)
    except Exception as e:
        _msgbox('CronosMac - Flask Error', str(e))


def _wait_flask(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def _open_edge_app(url):
    for path in [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    ]:
        if os.path.exists(path):
            subprocess.Popen([path, f'--app={url}', '--window-size=1280,820'])
            return True
    try:
        subprocess.Popen(f'start msedge --app={url}', shell=True)
        return True
    except Exception:
        return False


def main():
    t = threading.Thread(target=_run_flask, daemon=True)
    t.start()

    if not _wait_flask(PORT):
        _msgbox('CronosMac - Error', 'Server did not start in 20 seconds.')
        return

    url = f'http://127.0.0.1:{PORT}'

    # Option 1: native window via pywebview
    try:
        import webview
        webview.create_window('CronosMac v18', url,
                              width=1280, height=820, min_size=(900, 600))
        webview.start()
        return
    except Exception as e:
        pass  # fall through to Edge

    # Option 2: Edge in app mode (looks like native window)
    if _open_edge_app(url):
        threading.Event().wait()
        return

    _msgbox('CronosMac - Error',
            'Could not open app window.\n'
            'Run: python -m pip install pywebview')


if __name__ == '__main__':
    main()
