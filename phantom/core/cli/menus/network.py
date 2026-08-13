"""cli/menus/network.py — Red"""
import socket
from cli.ui import clear, line, pause, table
from phantom_core import PORT, tor_status
from session import PhantomSession

def network_menu(session: PhantomSession) -> None:
    while True:
        clear()
        transport = tor_status()
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "desconocida"

        print(f"\n  PHANTOM  >  Red")
        print(line())
        print(f"  transporte   {transport}  :{PORT}")
        print(f"  tu IP        {local_ip}")
        print(line())
        print("  [1] Escuchar   Esperar conexiones entrantes")
        print("  [2] Conectar   Conectarse a otro nodo por IP")
        print("  [3] Encuentros Ver historial")
        print("  [0] Volver")
        print()

        c = input("  > ").strip()
        if c == "0":   break
        elif c == "1": _listen(session)
        elif c == "2": _connect(session)
        elif c == "3": _encounters(session)


def _listen(session: PhantomSession) -> None:
    import phantom_node
    import threading

    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "—"

    clear()
    print(f"\n  Escuchando en puerto {PORT}.")
    print(f"  Tu IP: {local_ip}")
    print(f"\n  Compartila con el otro nodo para que se conecte.")
    print(line())
    print("  [1] Detener listener")
    print("  (los encuentros aparecen aqui abajo)\n")

    stop_event = threading.Event()

    def _run_listener():
        try:
            phantom_node.listen(
                store=session.store,
                encounter_log=session.encounter_log,
                identity=session.identity,
                pulse_ledger=session.pulse_ledger,
                contact_book=session.contact_book,
                dm_store=session.dm_store,
            )
        except Exception:
            pass

    t = threading.Thread(target=_run_listener, daemon=True)
    t.start()

    try:
        while t.is_alive():
            choice = input("  > ").strip()
            if choice == "1":
                break
    except KeyboardInterrupt:
        pass

    print("\n  Listener detenido.")
    pause()


def _connect(session: PhantomSession) -> None:
    import phantom_node
    clear()
    print("\n  PHANTOM  >  Red  >  Conectar")
    print(line())
    print()
    host = input("  IP del nodo (ej. 192.168.1.15): ").strip()
    if not host:
        return

    parts = host.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        print("\n  IP invalida.")
        pause()
        return

    print(f"\n  Conectando a {host}:{PORT}...")
    try:
        phantom_node.connect(
            store=session.store,
            encounter_log=session.encounter_log,
            host=host,
            identity=session.identity,
            pulse_ledger=session.pulse_ledger,
            contact_book=session.contact_book,
            dm_store=session.dm_store,
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n  Error: {e}")
        pause()
        return

    encounters = session.encounter_log.load()
    if encounters:
        last = encounters[-1]
        print()
        print(line())
        print("  Encuentro completado.")
        print(f"  Enviados:   {last.get('sent', 0)} sello(s)")
        print(f"  Recibidos:  {last.get('received', 0)} sello(s)")
        print(line())
    pause()


def _encounters(session: PhantomSession) -> None:
    clear()
    encounters = session.encounter_log.load()
    if not encounters:
        print("\n  Sin encuentros todavia.")
        pause()
        return

    enc = sorted(encounters, key=lambda e: e.get("moment",""), reverse=True)
    print(f"\n  PHANTOM  >  Encuentros           {len(enc)} en total")
    print(line())
    print()
    rows = [
        [str(i),
         e.get("moment","")[:16].replace("T"," "),
         str(e.get("peer","—"))[:20],
         str(e.get("sent",0)),
         str(e.get("received",0))]
        for i, e in enumerate(enc, 1)
    ]
    table(["#","momento","nodo","env","rec"], rows, [3,16,20,4,4])
    pause()
