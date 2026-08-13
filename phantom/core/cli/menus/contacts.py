"""cli/menus/contacts.py — Contactos y DMs"""
import json
import getpass
from cli.ui import clear, line, rule, pause, table, multiline_input
from phantom_core import create_dm, decrypt_dm, verify_contact_card
from session import PhantomSession


def contacts_menu(session: PhantomSession) -> None:
    while True:
        clear()
        contacts   = session.contact_book.all()
        pulses     = session.pulse_ledger.load()
        dm_capable = {fp: c for fp, c in contacts.items() if c.get("enc_pubkey_b64")}

        print(f"\n  PHANTOM  >  Contactos")
        print(line())
        print(f"  con contact card   {len(contacts)}   (pueden recibir DMs)")
        print(f"  conocidos por pulso {len(pulses)}   (presencia en la red)")
        print(line())
        print("  [1] Ver todos")
        print("  [2] Ver nodos en la red (pulsos)")
        print("  [3] Mensajes recibidos")
        print("  [4] Enviar mensaje")
        print("  [5] Importar contact card")
        print("  [6] Exportar mi contact card")
        print("  [0] Volver")
        print()

        c = input("  > ").strip()
        if c == "0":   break
        elif c == "1": _list_contacts(session)
        elif c == "2": _list_pulses(session)
        elif c == "3": _dms(session)
        elif c == "4": _send(session, dm_capable)
        elif c == "5": _import_card(session)
        elif c == "6": _export_card(session)


def _list_contacts(session):
    clear()
    contacts = session.contact_book.all()
    if not contacts:
        print("\n  Sin contact cards.")
        print("  Los contactos se agregan automaticamente durante los encuentros.")
        print("  O importa una con la opcion [5].")
        pause(); return

    print(f"\n  {len(contacts)} contacto(s) con contact card\n")
    print(line())
    for fp, card in contacts.items():
        name    = card.get("node_name") or "[sin nombre]"
        has_dm  = "DM" if card.get("enc_pubkey_b64") else "solo presencia"
        moment  = card.get("moment","")[:10]
        print(f"\n  {name}")
        print(f"  fp      {fp[:32]}...")
        print(f"  visto   {moment}   [{has_dm}]")
    print()
    pause()


def _list_pulses(session):
    clear()
    pulses = session.pulse_ledger.load()
    if not pulses:
        print("\n  Sin pulsos conocidos.")
        pause(); return

    print(f"\n  {len(pulses)} nodo(s) conocidos por pulso\n")
    print(line())
    rows = []
    for fp, pulse in pulses.items():
        moment  = pulse.get("moment","")[:16].replace("T"," ")
        address = pulse.get("address","—")
        rows.append([fp[:16]+"...", address, moment])
    table(["fingerprint","direccion","ultimo pulso"], rows, [18,22,16])
    print()
    pause()


def _dms(session):
    clear()
    if not session.identity:
        print("\n  Sin identidad."); pause(); return
    try:
        dms = session.dm_store.load()
    except Exception as e:
        print(f"\n  Error: {e}"); pause(); return
    if not dms:
        print("\n  Sin mensajes.")
        print("  Los DMs llegan durante los encuentros.")
        pause(); return

    dms = sorted(dms, key=lambda d: d.get("timestamp",""), reverse=True)
    print(f"\n  {len(dms)} mensaje(s)\n")
    print(line())
    for dm in dms:
        ts   = dm.get("timestamp","")[:16].replace("T"," ")
        fp   = dm.get("from_fingerprint","?")[:16]
        try:
            text = decrypt_dm(session.identity, dm)
            preview = (text or "")[:70]
        except Exception:
            preview = "[cifrado — necesitas la identidad correcta]"
        print(f"\n  {ts}  de {fp}...")
        print(f"  {preview}")
    print()
    pause()


def _send(session, dm_capable):
    clear()
    if not session.identity:
        print("\n  Sin identidad."); pause(); return

    if not dm_capable:
        print("\n  Sin contactos con clave de cifrado.")
        print()
        print("  Para enviar DMs necesitas una contact card completa del")
        print("  destinatario. Ocurre automaticamente en un encuentro.")
        print("  O pedi que te compartan su contact card (opcion [5]).")
        pause(); return

    cl = list(dm_capable.items())
    print("\n  Destinatario:\n")
    for i,(fp,card) in enumerate(cl,1):
        name = card.get("node_name") or "[sin nombre]"
        print(f"  [{i}] {name}  {fp[:16]}...")
    print()

    c = input("  Numero: ").strip()
    if not c.isdigit() or not (1 <= int(c) <= len(cl)):
        return
    fp, card = cl[int(c)-1]
    enc_pk = card.get("enc_pubkey_b64")

    name = card.get("node_name") or fp[:16]
    print(f"\n  Mensaje para {name}:")
    print("  (Enter vacio x2 para enviar)\n")

    lines = []
    empty = 0
    while True:
        l = input("  > ")
        if l == "":
            empty += 1
            if empty >= 2: break
            lines.append("")
        else:
            empty = 0
            lines.append(l)
    msg = "\n".join(lines).strip()
    if not msg:
        print("\n  Cancelado."); pause(); return

    try:
        dm = create_dm(session.identity, fp, enc_pk, msg)
        session.dm_store.store(dm)
        print("\n  Mensaje en cola.")
        print("  Se entregara en el proximo encuentro con ese nodo.")
        print("  El carrier no puede leer el contenido.")
    except Exception as e:
        print(f"\n  Error: {e}")
    pause()


def _import_card(session):
    """Importar contact card desde JSON pegado o archivo."""
    clear()
    print("\n  PHANTOM  >  Importar contact card")
    print(line())
    print()
    print("  Pega el JSON de la contact card (una linea) o una ruta a un archivo:")
    print()
    raw = input("  > ").strip()
    if not raw:
        return

    # File path?
    import os
    if os.path.exists(raw):
        try:
            with open(raw) as f:
                raw = f.read().strip()
        except Exception as e:
            print(f"\n  No pude leer el archivo: {e}")
            pause(); return

    try:
        card = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"\n  JSON invalido: {e}")
        pause(); return

    if not verify_contact_card(card):
        print("\n  Contact card invalida — la firma no verifica.")
        print("  Puede haber sido modificada o no es una card de Phantom.")
        pause(); return

    added = session.contact_book.record(card)
    name  = card.get("node_name") or card.get("fingerprint","?")[:16]
    print()
    if added:
        print(f"  Contacto agregado: {name}")
        has_dm = "puede recibir DMs" if card.get("enc_pubkey_b64") else "sin clave de cifrado"
        print(f"  [{has_dm}]")
    else:
        print(f"  Ya tenes una card de {name} igual o mas reciente.")
    pause()


def _export_card(session):
    """Mostrar tu propia contact card para compartir."""
    clear()
    if not session.identity:
        print("\n  Sin identidad."); pause(); return

    try:
        from phantom_core import create_contact_card
        card = create_contact_card(session.identity)
        card_json = json.dumps(card, ensure_ascii=False)
    except Exception as e:
        print(f"\n  Error generando card: {e}")
        pause(); return

    print("\n  PHANTOM  >  Mi contact card")
    print(line())
    print()
    print("  Compartila con quien quieras que pueda mandarte DMs.")
    print("  Pueden importarla con la opcion [5] del menu de contactos.")
    print()
    print(line("-"))
    # Wrap for readability
    import textwrap
    for chunk in textwrap.wrap(card_json, 68):
        print(f"  {chunk}")
    print(line("-"))
    print()
    print(f"  Nombre:       {session.node_name}")
    print(f"  Fingerprint:  {session.fingerprint[:32]}...")
    print(f"  DMs:          {'habilitados' if card.get('enc_pubkey_b64') else 'no disponible'}")
    print()
    pause()
