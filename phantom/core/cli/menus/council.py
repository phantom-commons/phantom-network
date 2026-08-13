"""cli/menus/council.py — Council"""
from cli.ui import clear, line, rule, pause
from session import PhantomSession
import os

PRESETS = {
    "1": ("Espejo",       "mirror"),
    "2": ("Constructor",  "builder"),
    "3": ("Critico",      "critic"),
    "4": ("Adversario",   "adversary"),
    "5": ("Lagos",        "lagos"),
    "6": ("Contraste",    "contraste"),
}
DESCS = {
    "1": "Lo que Phantom realmente es hoy.",
    "2": "Que construirias primero y por que.",
    "3": "Que voz falta. Quien no esta en la sala.",
    "4": "Tres ataques reales. El fork filosofico.",
    "5": "Puede ella usarlo hoy? La protege?",
    "6": "Verificar cada afirmacion contra la realidad.",
}

def council_menu(session: PhantomSession) -> None:
    while True:
        clear()
        print("\n  PHANTOM  >  Council")
        print(line())
        print("  No esta aqui para validar.")
        print("  Esta aqui para ver lo que otros no ven.")
        print(line())
        for k,(label,_) in PRESETS.items():
            print(f"  [{k}] {label:<14} {DESCS[k]}")
        print()
        print("  [7] Pregunta libre")
        print("  [8] Consejo completo")
        print("  [0] Volver")
        print()
        c = input("  > ").strip()
        if c == "0": break
        elif c == "7": _free()
        elif c == "8": _full()
        elif c in PRESETS: _preset(PRESETS[c][1], PRESETS[c][0])

def _detect_backend():
    try:
        import phantom_council as pc
    except ImportError:
        print("\n  phantom_council no encontrado.")
        pause(); return None, None, None, None

    try:
        import requests
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if r.ok:
            print("\n  Backend: Ollama (local)")
            return pc, "local", None, "llama3"
    except Exception:
        pass
    try:
        client = pc.get_client()
        if client:
            print("\n  Backend: Anthropic API")
            return pc, "external", client, None
    except Exception:
        pass

    print("\n  Sin backend de IA disponible.")
    print("  Opciones:")
    print("    Ollama:        ollama serve  (local, gratis)")
    print("    Anthropic API: ANTHROPIC_API_KEY en el entorno")
    pause(); return None, None, None, None

def _ask(pc, client_type, client, model, repo_text, r_hash, question, title=""):
    if title:
        print(f"\n  {rule(title)}")
    print()
    print("  Deliberando...", end="", flush=True)
    try:
        if client_type == "local":
            response = pc.send_local(repo_text, question, model=model)
        else:
            response = pc.send_external(client, repo_text, question)
        print("\r" + " "*20 + "\r", end="")
        # Word-wrap output
        import textwrap
        for line_text in response.split("\n"):
            if line_text.strip():
                for wrapped in textwrap.wrap(line_text, width=64):
                    print(f"  {wrapped}")
            else:
                print()
    except Exception as e:
        print(f"\n  Error: {e}")

def _preset(key, label):
    pc, client_type, client, model = _detect_backend()
    if pc is None: return
    repo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","..","..","..",".")
    repo_text = pc.read_repository(repo_path)
    r_hash = pc.repo_hash(repo_text)
    question = pc.PRESETS[key]
    clear()
    print(line())
    _ask(pc, client_type, client, model, repo_text, r_hash, question, label)
    print()
    print(line())
    pause()

def _free():
    pc, client_type, client, model = _detect_backend()
    if pc is None: return
    clear()
    print()
    lines = []
    print("  Pregunta (Enter vacio x2 para enviar):\n")
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
    question = "\n".join(lines).strip()
    if not question: return
    repo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","..","..","..",".")
    repo_text = pc.read_repository(repo_path)
    r_hash = pc.repo_hash(repo_text)
    print(line())
    _ask(pc, client_type, client, model, repo_text, r_hash, question)
    print(line())
    pause()

def _full():
    pc, client_type, client, model = _detect_backend()
    if pc is None: return
    repo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","..","..","..",".")
    repo_text = pc.read_repository(repo_path)
    r_hash = pc.repo_hash(repo_text)
    for k,(label,key) in PRESETS.items():
        question = pc.PRESETS[key]
        clear()
        print(line())
        _ask(pc, client_type, client, model, repo_text, r_hash, question, label)
        print(line())
        if input("\n  Continuar? [Enter/n]: ").strip().lower() == "n":
            break
    pause()
