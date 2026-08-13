"""
cli/unlock.py — Passphrase y derivacion de clave.

El unico lugar que pide la passphrase.
Devuelve un KeyManager listo. Todo lo demas lo recibe.
"""
import os
import sys

from cli.ui import ask_secret, pause, Spinner, line
from phantom_core import (
    KeyManager, SealStore,
    SALT_FILE, CRYPTO_AVAILABLE,
    get_or_create_salt, derive_key,
)


def unlock() -> tuple:
    """
    Pide passphrase, deriva clave, devuelve (km, is_new_node).
    is_new_node = True  -> primer arranque
    is_new_node = False -> nodo existente
    """
    km = KeyManager()
    is_new = not os.path.exists(SALT_FILE)

    if not CRYPTO_AVAILABLE:
        print()
        print("  [!] cryptography no instalado.")
        print("      Tus sellos se guardaran en texto plano.")
        print("      Para cifrar: pip install cryptography")
        print()
        return km, is_new

    if is_new:
        _setup_new(km)
    else:
        _unlock_existing(km)

    return km, is_new


def _setup_new(km: KeyManager) -> None:
    print()
    print(line())
    print("  Primera vez en este nodo.")
    print()
    print("  Podes proteger tus sellos con una passphrase.")
    print("  Phantom no guarda copia. Si la olvidás, los sellos")
    print("  no se pueden recuperar.")
    print()
    print("  (Enter sin escribir = correr sin cifrado)")
    print(line())
    print()

    passphrase = ask_secret("Passphrase nueva: ")

    if not passphrase:
        print("\n  Sin cifrado. Sellos guardados en texto plano.\n")
        return

    confirm = ask_secret("Confirmar passphrase: ")
    if passphrase != confirm:
        print("\n  Las passphrases no coinciden. Saliendo.\n")
        sys.exit(1)

    _derive(km, passphrase)
    print("  Nodo protegido.\n")


def _unlock_existing(km: KeyManager) -> None:
    print()
    passphrase = ask_secret("Passphrase: ")

    if not passphrase:
        print("\n  Sin passphrase — sellos cifrados no legibles.\n")
        return

    _derive(km, passphrase)
    _verify(km)


def _derive(km: KeyManager, passphrase: str) -> None:
    salt = get_or_create_salt()
    with Spinner("Derivando clave..."):
        km._key = derive_key(passphrase, salt)


def _verify(km: KeyManager) -> None:
    try:
        SealStore(km).load()
    except ValueError:
        print("\n  Passphrase incorrecta.\n")
        sys.exit(1)
