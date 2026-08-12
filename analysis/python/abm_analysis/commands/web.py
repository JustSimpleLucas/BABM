"""Local statistics dashboard command: parser and handler."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path


#: Seconds to wait before opening a browser, giving uvicorn time to bind the
#: port. A tab that opens fractionally early shows a connection error and has
#: to be reloaded by hand, which defeats the convenience.
BROWSER_LAUNCH_DELAY_SECONDS = 1.0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``web`` command."""

    web_parser = subparsers.add_parser(
        "web",
        help="Serve a local dashboard for browsing archived runs and their market statistics.",
    )
    web_parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="Directory searched for archived runs. Defaults to ./data.",
    )
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "Interface to bind. Defaults to the loopback address so unpublished "
            "results are not exposed on the network."
        ),
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on. Defaults to 8000.",
    )
    web_parser.add_argument(
        "--no-browser",
        dest="open_browser",
        action="store_false",
        help="Do not open a browser window on start.",
    )
    web_parser.set_defaults(handler=handle_web, open_browser=True)


def handle_web(args: argparse.Namespace) -> int:
    """Start the read-only dashboard server for an archive root."""

    from abm_analysis.web import serve

    data_root = args.data_root.expanduser().resolve()
    if not data_root.is_dir():
        print(f"Data root does not exist: {data_root}")
        return 1

    url = f"http://{_display_host(args.host)}:{args.port}/"
    print(f"Archive root: {data_root}")
    print(f"Dashboard: {url}")
    print("Press Ctrl+C to stop.")

    if args.open_browser:
        threading.Timer(BROWSER_LAUNCH_DELAY_SECONDS, webbrowser.open, args=(url,)).start()

    try:
        serve(data_root, host=args.host, port=args.port)
    except KeyboardInterrupt:  # pragma: no cover - interactive interruption.
        print("\nDashboard stopped.")
    return 0


def _display_host(host: str) -> str:
    """Return a host that is usable in a browser address bar.

    Binding ``0.0.0.0`` listens on every interface but is not a destination a
    browser can open, so the printed URL points at the loopback address.
    """

    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host
