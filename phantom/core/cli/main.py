"""
cli/main.py — Menu principal.

Llamado desde phantom.py, que ya configuro el sys.path.
"""
import sys

from cli.ui import clear, logo, line, rule, pause
from cli.unlock import unlock
from session import PhantomSession
from phantom_core import PHANTOM_VERSION


MENU = [
    ("1", "Sellos",    "Sellar, verificar, explorar"),
    ("2", "Red",       "Escuchar, conectar, encuentros"),
    ("3", "Wallet",    "Identidad economica, direcciones"),
    ("4", "Contactos", "Libro de contactos, mensajes"),
    ("5", "Diario",    "Entradas privadas, reflexion"),
    ("6", "Council",   "Deliberacion con el consejo"),
    ("0", "Salir",     ""),
]


def main() -> None:
    try:
        _run()
    except KeyboardInterrupt:
        print("\n\n  Interrumpido.\n")
        sys.exit(0)


def _run() -> None:
    # ── Pantalla de unlock ────────────────────────────────────
    clear()
    print(logo())
    print(f"\n  v{PHANTOM_VERSION}")
    print()

    km, is_new = unlock()

    # ── Abrir sesion ──────────────────────────────────────────
    import io, contextlib
    from phantom_core import NODE_KEY_FILE
    import os

    is_new_identity = not os.path.exists(NODE_KEY_FILE)

    if is_new_identity:
        # Nueva identidad — _load_or_create_identity necesita
        # hablar y escuchar directamente. No suprimimos.
        print()
        session = PhantomSession.open(km)
        print()
    else:
        # Identidad existente — suprimir prints de phantom_core
        print("  Abriendo nodo...", end="", flush=True)
        _sink = io.StringIO()
        with contextlib.redirect_stdout(_sink), contextlib.redirect_stderr(_sink):
            session = PhantomSession.open(km)
        print(" listo.\n")

    if is_new and session.identity:
        _welcome(session)

    # ── Loop principal ────────────────────────────────────────
    while True:
        _print_header(session)
        _print_menu()

        try:
            choice = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cerrando.\n")
            break

        if not _route(choice, session):
            break


def _print_header(session: PhantomSession) -> None:
    clear()
    print(logo())
    stats = session.summary()
    print()
    print(line())
    print(f"  identidad   {session.node_name}  [{session.fingerprint_short}]")
    print(f"  datos       {stats['seals']} sellos  .  "
          f"{stats['encounters']} encuentros  .  "
          f"{stats['contacts']} contactos")
    print(f"  cifrado     {'activo' if stats['encrypted'] else 'inactivo'}")
    print(line())
    print()


def _print_menu() -> None:
    for key, label, desc in MENU:
        if key == "0":
            print(f"  [0] Salir")
        else:
            print(f"  [{key}] {label:<12} {desc}")
    print()


def _route(choice: str, session: PhantomSession) -> bool:
    if choice == "0":
        print("\n  Cerrando nodo.\n")
        return False
    elif choice == "1":
        from cli.menus.seals import seals_menu
        seals_menu(session)
    elif choice == "2":
        from cli.menus.network import network_menu
        network_menu(session)
    elif choice == "3":
        from cli.menus.wallet import wallet_menu
        wallet_menu(session)
    elif choice == "4":
        from cli.menus.contacts import contacts_menu
        contacts_menu(session)
    elif choice == "5":
        from cli.menus.diary import diary_menu
        diary_menu(session)
    elif choice == "6":
        from cli.menus.council import council_menu
        council_menu(session)
    else:
        print("  Opcion no valida.")
    return True


def _welcome(session: PhantomSession) -> None:
    print(line())
    print("  Nodo creado.")
    print()
    print(f"  Nombre:       {session.node_name}")
    print(f"  Fingerprint:  {session.fingerprint}")
    print()
    print("  Esta es tu identidad criptografica en la red Phantom.")
    print(line())
    pause()
