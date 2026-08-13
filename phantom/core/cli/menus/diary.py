"""cli/menus/diary.py — Diario"""
from cli.ui import clear, line, rule, pause, table, multiline_input
from phantom_diary import make_entry, verify_entry
from session import PhantomSession

MOODS = ["","claro","oscuro","incierto","resuelto","urgente","sereno"]

def diary_menu(session: PhantomSession) -> None:
    while True:
        clear()
        count = session.diary_store.count()
        print(f"\n  PHANTOM  >  Diario              {count} entrada(s)")
        print(line())
        print("  [1] Nueva entrada")
        print("  [2] Entradas recientes")
        print("  [3] Buscar")
        print("  [0] Volver")
        print()
        c = input("  > ").strip()
        if c == "0":   break
        elif c == "1": _new(session)
        elif c == "2": _recent(session)
        elif c == "3": _search(session)

def _new(session):
    clear()
    print("\n  PHANTOM  >  Diario  >  Nueva entrada")
    print(line())
    print()
    print("  Tono: " + "  ".join(f"[{i}] {m}" for i,m in enumerate(MOODS[1:],1)))
    mc = input("\n  Tono [0]: ").strip() or "0"
    mood = MOODS[int(mc)] if mc.isdigit() and int(mc) < len(MOODS) else None
    tr = input("  Tags (coma, opcional): ").strip()
    tags = [t.strip() for t in tr.split(",") if t.strip()] or None
    print()
    text = multiline_input("Entrada")
    if not text:
        print("\n  Cancelado."); pause(); return
    entry = make_entry(text, tags=tags, mood=mood)
    session.diary_store.save(entry)
    print()
    print(line())
    print("  Entrada guardada y sellada.")
    print(f"  stamp    {entry.get('stamp','')[:32]}...")
    print(f"  momento  {entry.get('moment','')[:19]}")
    print(line())
    pause()

def _recent(session):
    clear()
    entries = session.diary_store.recent(10)
    if not entries:
        print("\n  Sin entradas."); pause(); return
    print(f"\n  PHANTOM  >  Diario  >  Recientes")
    print(line())
    for i,e in enumerate(reversed(entries),1):
        moment = e.get("moment","")[:16].replace("T"," ")
        mood = e.get("mood","")
        text = e.get("text","")[:80].replace("\n"," ")
        print(f"\n  {i}. {moment}{'  '+mood if mood else ''}")
        print(f"     {text}")
    print()
    c = input("  Numero para ver completa, Enter para volver: ").strip()
    if c.isdigit():
        el = list(reversed(entries))
        idx = int(c)-1
        if 0 <= idx < len(el):
            _detail(el[idx])

def _detail(entry):
    clear()
    moment = entry.get("moment","")[:19].replace("T"," ")
    valid = verify_entry(entry)
    print(f"\n  {moment}")
    print(line())
    print()
    print(entry.get("text",""))
    print()
    print(line("-"))
    print(f"  integridad  {'[ok] valida' if valid else '[!!] ALTERADA'}")
    if entry.get("mood"):   print(f"  tono        {entry['mood']}")
    if entry.get("tags"):   print(f"  tags        {', '.join(entry['tags'])}")
    print(line())
    pause()

def _search(session):
    clear()
    print()
    q = input("  Buscar en diario: ").strip()
    if not q: return
    results = session.diary_store.search(q)
    print()
    if not results:
        print(f"  Sin resultados para '{q}'.")
    else:
        for e in results:
            moment = e.get("moment","")[:16].replace("T"," ")
            print(f"  {moment}  {e.get('text','')[:60]}")
    pause()
