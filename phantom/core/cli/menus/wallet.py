"""cli/menus/wallet.py — Wallet"""
import getpass
from cli.ui import clear, line, pause, ask
from session import PhantomSession

COINS = ["BTC","ETH","LTC","DOGE"]

def wallet_menu(session: PhantomSession) -> None:
    while True:
        clear()
        wallet = _load(session)
        addr = wallet.address if wallet else "sin wallet"
        print(f"\n  PHANTOM  >  Wallet")
        print(line())
        print(f"  direccion   {addr}")
        print(line())
        if wallet is None:
            print("  [1] Crear wallet")
            print("  [2] Importar desde frase")
        else:
            print("  [1] Ver direccion Phantom")
            print("  [2] Ver direccion externa  (BTC/ETH/LTC/DOGE)")
            print("  [3] Ver frase de recuperacion")
            print("  [4] Importar otra wallet")
        print("  [0] Volver")
        print()

        c = input("  > ").strip()
        if c == "0": break
        elif wallet is None:
            if c == "1": _create(session)
            elif c == "2": _import(session)
        else:
            if c == "1": _show_address(wallet)
            elif c == "2": _show_external(wallet)
            elif c == "3": _show_mnemonic(session)
            elif c == "4": _import(session)

def _load(session):
    if session.wallet: return session.wallet
    try:
        from phantom_wallet import PhantomWallet
        w = PhantomWallet.load(session.km.key)
        session.wallet = w
        return w
    except Exception:
        return None

def _create(session):
    clear()
    print("\n  PHANTOM  >  Wallet  >  Crear")
    print(line())
    print()
    print("  Se generaran 24 palabras de recuperacion.")
    print()
    print("  [!] Anotalas en papel. Phantom no guarda copia.")
    print("      Sin ellas, la wallet no se puede recuperar.")
    print("      Esta frase NUNCA viajara por internet.")
    print()
    confirm = input("  Escribi ENTIENDO para continuar: ").strip().upper()
    if confirm != "ENTIENDO":
        print("\n  Cancelado.")
        pause()
        return
    try:
        from phantom_wallet import PhantomWallet
        wallet, mnemonic = PhantomWallet.generate_with_mnemonic()
    except Exception as e:
        print(f"\n  Error: {e}")
        pause()
        return

    words = mnemonic.split()
    print()
    print(line("="))
    print("  !!  FRASE DE RECUPERACION — 24 PALABRAS  !!")
    print("  !!  Anotalas ahora. Phantom no guarda copia.  !!")
    print(line("="))
    print()
    for row in range(6):
        parts = []
        for col in range(4):
            idx = col * 6 + row
            if idx < len(words):
                parts.append(f"  {idx+1:2}. {words[idx]:<12}")
        print("".join(parts))
    print()
    print(line("="))
    print()
    c = input("  Escribi GUARDE LA FRASE para continuar: ").strip().upper()
    if c != "GUARDE LA FRASE":
        print("\n  Cancelado. Wallet no guardada.")
        pause()
        return
    wallet.save(mnemonic, session.km.key)
    session.wallet = wallet
    print(f"\n  Wallet creada: {wallet.address}")
    pause()

def _import(session):
    clear()
    print("\n  PHANTOM  >  Wallet  >  Importar")
    print(line())
    print()
    mnemonic = getpass.getpass("  Frase (24 palabras): ")
    mnemonic = " ".join(mnemonic.strip().split())
    try:
        from phantom_wallet import PhantomWallet
        wallet = PhantomWallet.from_mnemonic(mnemonic)
        wallet.save(mnemonic, session.km.key)
        session.wallet = wallet
        print(f"\n  Importada: {wallet.address}")
    except Exception as e:
        print(f"\n  Error: {e}")
    pause()

def _show_address(wallet):
    clear()
    print("\n  Direccion Phantom:")
    print(f"\n  {wallet.address}")
    print()
    print("  Usa esta direccion para recibir en la red Phantom.")
    pause()

def _show_external(wallet):
    clear()
    print("\n  Coin: " + "  ".join(f"[{i}] {c}" for i,c in enumerate(COINS,1)))
    print()
    c = input("  Selecciona [1-4]: ").strip()
    coin_map = {str(i): c for i,c in enumerate(COINS,1)}
    coin = coin_map.get(c)
    if not coin: return
    try:
        result = wallet.external(coin)
        print(f"\n  {coin}: {result['address']}")
        print(f"  Path: {result.get('path','—')}")
    except Exception as e:
        print(f"\n  Error: {e}")
    pause()

def _show_mnemonic(session):
    clear()
    print("\n  [!] Asegurate que nadie este mirando tu pantalla.")
    print()
    pw = getpass.getpass("  Confirma tu passphrase: ")
    from phantom_core import derive_key, get_or_create_salt, SALT_FILE, CRYPTO_AVAILABLE
    import os
    if CRYPTO_AVAILABLE and os.path.exists(SALT_FILE):
        salt = get_or_create_salt()
        if derive_key(pw, salt) != session.km.key:
            print("\n  Passphrase incorrecta.")
            pause()
            return
    try:
        from phantom_wallet import PhantomWallet, WALLET_KEY_FILE
        import json
        from phantom_core import decrypt_data
        with open(WALLET_KEY_FILE) as f:
            stored = json.load(f)
        if stored.get("plaintext"):
            mnemonic = stored["mnemonic"]
        else:
            mnemonic = decrypt_data(stored, session.km.key).decode()
        words = mnemonic.split()
        print()
        print(line("="))
        print("  !!  FRASE DE RECUPERACION — 24 PALABRAS  !!")
        print(line("="))
        print()
        for row in range(6):
            parts = []
            for col in range(4):
                idx = col*6+row
                if idx < len(words):
                    parts.append(f"  {idx+1:2}. {words[idx]:<12}")
            print("".join(parts))
        print()
        print(line("="))
    except Exception as e:
        print(f"\n  Error: {e}")
    pause()
    clear()
