"""cli/menus/seals.py — Sellos"""
import sys

from cli.ui import clear, line, rule, pause, table, multiline_input, ask
from phantom_core import (
    seal, verify,
    MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL,
    CHANNELS, MAX_IDEA_LENGTH,
)
from session import PhantomSession

MODES = {
    "1": (MODE_PRIVATE,   "privado",    "Solo existe en tu nodo."),
    "2": (MODE_PERMANENT, "permanente", "Viaja a otros nodos."),
    "3": (MODE_EPHEMERAL, "efimero",    "No se guarda. Desaparece al cerrar."),
}


def seals_menu(session: PhantomSession) -> None:
    while True:
        clear()
        count = session.store.count()
        print(f"\n  PHANTOM  >  Sellos                    {count} sellos")
        print(line())
        print("  [1] Nuevo sello")
        print("  [2] Ver sellos")
        print("  [3] Verificar sello")
        print("  [4] Buscar")
        print("  [0] Volver")
        print()

        c = input("  > ").strip()
        if c == "0":  break
        elif c == "1": _new(session)
        elif c == "2": _list(session)
        elif c == "3": _verify()
        elif c == "4": _search(session)


def _new(session: PhantomSession) -> None:
    clear()
    print("\n  PHANTOM  >  Sellos  >  Nuevo")
    print(line())
    print()
    for k, (_, label, desc) in MODES.items():
        print(f"  [{k}] {label:<12} {desc}")
    print()
    mc = input("  Modo [1]: ").strip() or "1"
    mode, label, _ = MODES.get(mc, MODES["1"])

    channel = None
    if mode == MODE_PERMANENT:
        print("\n  Canal (opcional):")
        for i, ch in enumerate(CHANNELS, 1):
            print(f"  [{i}] {ch}")
        print("  [0] Sin canal")
        cc = input("\n  Canal [0]: ").strip()
        ch_map = {str(i): ch for i, ch in enumerate(CHANNELS, 1)}
        channel = ch_map.get(cc)

    print()
    idea = multiline_input("Pensamiento")

    if not idea:
        print("\n  Cancelado.")
        pause()
        return

    if len(idea) > MAX_IDEA_LENGTH:
        print(f"\n  Demasiado largo ({len(idea):,} chars).")
        pause()
        return

    entry = seal(idea, mode=mode, channel=channel)
    if mode != MODE_EPHEMERAL:
        session.store.save(entry)

    print()
    print(line())
    print("  Sellado.")
    print()
    print(f"  stamp    {entry['stamp']}")
    print(f"  momento  {entry['moment']}")
    print(f"  modo     {label}")
    if channel:
        print(f"  canal    {channel}")
    print(line())
    pause()


def _list(session: PhantomSession) -> None:
    clear()
    seals = session.store.load()
    if not seals:
        print("\n  Sin sellos todavia.")
        pause()
        return

    seals = sorted(seals, key=lambda s: s.get("moment",""), reverse=True)
    print(f"\n  PHANTOM  >  Sellos                    {len(seals)} sellos")
    print(line())
    print()

    rows = []
    for i, s in enumerate(seals, 1):
        rows.append([
            str(i),
            s.get("stamp","")[:12] + "...",
            s.get("mode", MODE_PERMANENT)[:10],
            s.get("moment","")[:16].replace("T"," "),
            s.get("idea","")[:40],
        ])
    table(["#","stamp","modo","momento","idea"], rows, [3,14,10,16,40])
    print()

    c = input("  Numero para detalle, Enter para volver: ").strip()
    if c.isdigit():
        idx = int(c) - 1
        if 0 <= idx < len(seals):
            _detail(seals[idx])


def _detail(entry: dict) -> None:
    clear()
    print("\n  PHANTOM  >  Sellos  >  Detalle")
    print(line())
    print()
    print(entry.get("idea",""))
    print()
    print(line("-"))
    print(f"  stamp    {entry.get('stamp','')}")
    print(f"  momento  {entry.get('moment','')}")
    print(f"  modo     {entry.get('mode','')}")
    if entry.get("channel"):
        print(f"  canal    {entry['channel']}")
    print()
    valid = verify(entry["idea"], entry["moment"], entry["stamp"])
    if valid:
        print("  [ok] Sello valido - contenido no alterado.")
    else:
        print("  [!!] Sello INVALIDO - contenido modificado.")
    print(line())
    pause()


def _verify() -> None:
    clear()
    print("\n  PHANTOM  >  Sellos  >  Verificar")
    print(line())
    print()
    stamp  = input("  Stamp (64 hex): ").strip()
    moment = input("  Momento (ISO):  ").strip()
    idea   = multiline_input("Idea")

    if not (stamp and moment and idea):
        print("\n  Datos incompletos.")
        pause()
        return

    valid = verify(idea, moment, stamp)
    print()
    print(line())
    if valid:
        print("  [ok] Sello VALIDO.")
    else:
        print("  [!!] Sello INVALIDO.")
    print(line())
    pause()


def _search(session: PhantomSession) -> None:
    clear()
    print()
    q = input("  Buscar en sellos: ").strip().lower()
    if not q:
        return
    results = [s for s in session.store.load()
               if q in s.get("idea","").lower()
               or q in s.get("channel","").lower()]
    print()
    if not results:
        print(f"  Sin resultados para '{q}'.")
    else:
        print(f"  {len(results)} resultado(s):\n")
        for s in results:
            moment = s.get("moment","")[:16].replace("T"," ")
            preview = s.get("idea","")[:60]
            print(f"  {moment}  {preview}")
    pause()
