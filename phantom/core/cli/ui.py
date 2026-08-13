"""
cli/ui.py — Presentacion en stdlib pura.

Sin dependencias externas. Solo print(), input(), os.
"""
import os
import sys
import getpass

# ── Ancho de terminal ────────────────────────────────────────

def terminal_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


# ── Logo adaptativo ──────────────────────────────────────────

LOGO_WIDE = r"""
  ██████╗ ██╗  ██╗ █████╗ ███╗  ██╗████████╗ ██████╗ ███╗  ███╗
  ██╔══██╗██║  ██║██╔══██╗████╗ ██║╚══██╔══╝██╔═══██╗████╗████║
  ██████╔╝███████║███████║██╔██╗██║   ██║   ██║   ██║██╔████╔██║
  ██╔═══╝ ██╔══██║██╔══██║██║╚████║   ██║   ██║   ██║██║╚██╔╝██║
  ██║     ██║  ██║██║  ██║██║ ╚███║   ██║    ██████╔╝██║ ╚═╝ ██║
  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝"""

LOGO_COMPACT = r"""
  +---------------------------------+
  |  P H A N T O M  N E T W O R K  |
  +---------------------------------+"""

LOGO_MINIMAL = "  [ PHANTOM NETWORK ]"


def logo() -> str:
    w = terminal_width()
    if w >= 68:
        return LOGO_WIDE
    elif w >= 36:
        return LOGO_COMPACT
    else:
        return LOGO_MINIMAL


# ── Separadores ──────────────────────────────────────────────

def line(char="═") -> str:
    w = min(terminal_width(), 68)
    return "  " + char * w


def rule(title="", char="─") -> str:
    w = min(terminal_width(), 68) - 2
    if not title:
        return "  " + char * w
    pad = w - len(title) - 2
    left = pad // 2
    right = pad - left
    return "  " + char * left + " " + title + " " + char * right


# ── Clear ────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


# ── Input helpers ────────────────────────────────────────────

def ask(prompt: str) -> str:
    return input(f"  {prompt}").strip()


def ask_secret(prompt: str) -> str:
    return getpass.getpass(f"  {prompt}")


def pause(msg="Enter para continuar..."):
    input(f"\n  {msg}")


def confirm(msg: str) -> bool:
    r = ask(f"{msg} [s/n]: ").lower()
    return r in ("s", "si", "y", "yes")


# ── Spinner de texto ─────────────────────────────────────────

import threading
import time
import itertools

class Spinner:
    """Spinner en texto plano para operaciones lentas (ej. scrypt)."""

    def __init__(self, msg: str = ""):
        self.msg = msg
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        frames = ["|", "/", "-", "\\"]
        for f in itertools.cycle(frames):
            if self._stop.is_set():
                break
            print(f"\r  {f}  {self.msg}", end="", flush=True)
            time.sleep(0.1)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        print(f"\r  ok  {self.msg}")


# ── Tabla simple ─────────────────────────────────────────────

def table(headers: list, rows: list, widths: list = None) -> None:
    """Imprime una tabla simple alineada."""
    if not rows:
        return

    # Calcular anchos si no se dieron
    if not widths:
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))

    # Limitar ancho total al terminal
    max_total = terminal_width() - 4
    total = sum(widths) + len(widths) * 2
    if total > max_total:
        # Recortar la última columna
        overflow = total - max_total
        widths[-1] = max(8, widths[-1] - overflow)

    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    sep = "  " + "  ".join("-" * w for w in widths)

    print(fmt.format(*[h[:widths[i]] for i, h in enumerate(headers)]))
    print(sep)
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            s = str(cell)
            w = widths[i] if i < len(widths) else 10
            cells.append((s[:w-1] + "…") if len(s) > w else s)
        print(fmt.format(*cells))


# ── Multiline input ──────────────────────────────────────────

def multiline_input(prompt="Texto") -> str:
    """Lee varias lineas hasta doble Enter vacio."""
    print(f"  {prompt} (Enter vacio x2 para terminar):\n")
    lines = []
    empty = 0
    while True:
        line = input("  > ")
        if line == "":
            empty += 1
            if empty >= 2:
                break
            lines.append("")
        else:
            empty = 0
            lines.append(line)
    return "\n".join(lines).strip()
