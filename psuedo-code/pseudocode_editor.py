#!/usr/bin/env python3
"""
PseudoCode Editor
=================

A single-file Python app that launches a browser-based pseudo-code editor styled
after the CLRS/Open University conventions described around pages 16-17 of the
uploaded textbook.

Why this approach:
- A browser editor is much easier than a native desktop GUI for typography,
  inline styling, line numbering, print layout, symbol replacement, and live
  formatting.
- Python still remains the entry point, so you can run one script and get the app.
- Export is HTML, which preserves typography much better than plain text.

Run:
    python pseudocode_editor.py

Then open:
    http://127.0.0.1:8765
"""

from flask import Flask, request, jsonify, render_template_string
import threading
import webbrowser
import socket
import time

APP = Flask(__name__)


@APP.route("/")
def index():
  HTML = ""
  with open("pce.html", "r", encoding="utf-8") as f:
      HTML = f.read()
      f.close()
  return render_template_string(HTML)


def _find_port(preferred: int = 8765) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 50)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("Could not find a free localhost port.")


def main() -> None:
    port = _find_port(8765)
    url = f"http://127.0.0.1:{port}"

    def open_browser_later():
        time.sleep(0.8)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser_later, daemon=True).start()
    print(f"PseudoCode Editor running at {url}")
    print("Press Ctrl+C to stop.")
    APP.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
