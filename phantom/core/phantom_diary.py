# phantom_diary.py — v0.1
#
# A private journal for Phantom Network.
#
# "Your thoughts belong to you."
#
# What this is:
#   A diary where each entry is sealed (SHA-256) and encrypted
#   (AES-256-GCM) on your device. The same cryptographic
#   guarantees as Phantom seals — but for longer, private writing.
#
# What makes it different from phantom_seed.py:
#   — Entries are long-form text, not single ideas
#   — Private by default, never propagated to the network
#   — Organized by date, searchable, browsable
#   — Each entry has a mood/tag (optional)
#   — The seal proves the entry existed unmodified at that moment
#
# AI (optional):
#   If Ollama is running locally (localhost:11434), you can ask
#   the AI to reflect on an entry or find patterns across entries.
#   If Ollama is not running — the diary works exactly the same.
#   The AI is a guest. The diary belongs to you.
#
# Lagos Protocol:
#   Works offline. Works on a secondhand Android phone in Termux.
#   No account. No server. No cloud sync. No ads.
#   A forgotten passphrase means lost entries — this is the protection.
#
# HISTORY:
#   v0.1 — March 12, 2026. First diary.

import hashlib
import json
import os
import sys
import textwrap
from datetime import datetime, timezone

from phantom_core import (
    PHANTOM_VERSION, KeyManager,
    encrypt_data, decrypt_data, CRYPTO_AVAILABLE,
    get_or_create_salt, DATA_DIR,
)

DIARY_VERSION = "0.1"
DIARY_FILE = os.path.join(DATA_DIR, "phantom_diary.json")

# ─────────────────────────────────────────────────────────
# ENTRY STRUCTURE
# ─────────────────────────────────────────────────────────

def _stamp_entry(entry):
    """Deterministic SHA-256 stamp over the entry's immutable fields."""
    canonical = json.dumps(
        {
            "text":   entry["text"],
            "moment": entry["moment"],
        },
        separators=(',', ':'),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def make_entry(text, tags=None, mood=None):
    """
    Create a new diary entry.
    Returns a dict ready to be stored.
    """
    if not text or not text.strip():
        raise ValueError("Cannot save an empty entry.")

    moment = datetime.now(timezone.utc).isoformat()
    entry = {
        "text":    text.strip(),
        "moment":  moment,
        "tags":    tags or [],
        "mood":    mood or "",
        "version": DIARY_VERSION,
    }
    entry["stamp"] = _stamp_entry(entry)
    return entry


def verify_entry(entry):
    """Verify that an entry has not been modified since it was written."""
    return _stamp_entry(entry) == entry.get("stamp", "")


# ─────────────────────────────────────────────────────────
# DIARY STORE
# ─────────────────────────────────────────────────────────

class DiaryStore:
    """
    Local encrypted diary storage.

    Entries are stored as a JSON array, encrypted as a single
    blob if a key is available. This means even the number of
    entries is hidden from anyone without the passphrase.

    The stamp on each entry proves it was not modified after
    writing — even by you. That is the seal's promise.
    """

    def __init__(self, key_manager):
        self._km = key_manager
        self._cache = None

    @property
    def key(self):
        return self._km.key

    def load(self):
        if self._cache is not None:
            return list(self._cache)

        if not os.path.exists(DIARY_FILE):
            self._cache = []
            return []

        with open(DIARY_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, dict) and raw.get("encrypted"):
            if self.key is None:
                print(" (Diary is encrypted — enter passphrase to read)")
                self._cache = []
                return []
            plaintext = decrypt_data(raw, self.key)
            entries = json.loads(plaintext.decode('utf-8'))
        else:
            entries = raw

        self._cache = entries
        return list(entries)

    def _persist(self, entries):
        if self.key is not None and CRYPTO_AVAILABLE:
            plaintext = json.dumps(entries, ensure_ascii=False).encode('utf-8')
            stored = encrypt_data(plaintext, self.key)
        else:
            stored = entries
        with open(DIARY_FILE, "w", encoding="utf-8") as f:
            json.dump(stored, f, indent=2, ensure_ascii=False)

    def save(self, entry):
        entries = self.load()
        entries.append(entry)
        self._cache = entries
        self._persist(entries)
        return True

    def count(self):
        return len(self.load())

    def search(self, query):
        """Return entries containing query (case-insensitive)."""
        q = query.lower()
        return [
            e for e in self.load()
            if q in e["text"].lower()
            or q in " ".join(e.get("tags", [])).lower()
            or q in e.get("mood", "").lower()
        ]

    def by_date(self, date_str):
        """Return entries for a given date (YYYY-MM-DD)."""
        return [
            e for e in self.load()
            if e["moment"].startswith(date_str)
        ]

    def recent(self, n=5):
        """Return the n most recent entries."""
        entries = self.load()
        return entries[-n:] if entries else []

    def integrity_check(self):
        """Verify all entries. Returns (valid, tampered_list)."""
        entries = self.load()
        valid = 0
        tampered = []
        for e in entries:
            if verify_entry(e):
                valid += 1
            else:
                tampered.append(e["moment"])
        return valid, tampered


# ─────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────

def _format_moment(moment_str):
    """Human-readable date from ISO moment."""
    try:
        # Handle various ISO formats
        clean = moment_str[:19].replace("T", " ")
        return clean
    except Exception:
        return moment_str


def _wrap(text, width=70, indent="  "):
    lines = text.split("\n")
    wrapped = []
    for line in lines:
        if line.strip() == "":
            wrapped.append("")
        else:
            for w in textwrap.wrap(line, width):
                wrapped.append(indent + w)
    return "\n".join(wrapped)


def _print_entry(entry, index=None, short=False):
    """Print one diary entry."""
    verified = "✓" if verify_entry(entry) else "✗ MODIFIED"
    moment = _format_moment(entry["moment"])
    tags = "  #" + "  #".join(entry["tags"]) if entry.get("tags") else ""
    mood = f"  [{entry['mood']}]" if entry.get("mood") else ""
    idx = f"[{index}] " if index is not None else ""

    print(f"\n {idx}{moment}{mood}{tags}  {verified}")
    print(f" {'─' * 60}")

    if short:
        preview = entry["text"][:120].replace("\n", " ")
        if len(entry["text"]) > 120:
            preview += "..."
        print(f"  {preview}")
    else:
        print(_wrap(entry["text"]))
        print(f"\n  stamp: {entry['stamp'][:32]}...")

    print()


# ─────────────────────────────────────────────────────────
# AI BRIDGE (optional)
#
# If Ollama is running at localhost:11434, we can ask it
# to reflect on entries. If not — nothing breaks.
# The diary is complete without it.
# ─────────────────────────────────────────────────────────

def _ollama_available():
    """Check if Ollama is reachable on localhost."""
    import socket as _socket
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", 11434))
        s.close()
        return result == 0
    except Exception:
        return False


def _ollama_ask(prompt, model="llama3"):
    """
    Send a prompt to Ollama and stream the response.
    Returns full response text.
    Nothing leaves your device.
    """
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode('utf-8')

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get("response", "").strip()
    except urllib.error.URLError:
        return None
    except Exception as e:
        return None


def ai_reflect(entry, model="llama3"):
    """
    Ask the local AI to reflect on a diary entry.
    Returns response text, or None if AI is unavailable.

    # GAP (ECHO.md): that document describes Echo as running on
    # "1 billion parameters... on an Android phone in Termux" — this
    # function's default is "llama3" (Ollama's default tag, commonly
    # 8B), and Ollama connecting to localhost:11434 usually implies
    # a PC, not the phone itself. This may describe two genuinely
    # different deployments (Echo the persona vs. whatever ran on-
    # phone — memory elsewhere ties the 1B/Termux description to
    # "Luna," not Echo), or it may just be stale. Worth resolving
    # which is actually true rather than leaving both claims stand.
    """
    if not _ollama_available():
        return None

    prompt = f"""You are a thoughtful, private journal companion.
The person has written this diary entry:

---
{entry['text']}
---

Respond with a brief, honest reflection. Ask one question that might help them go deeper.
Do not be generic. Respond to what they actually wrote.
Keep your response under 150 words."""

    return _ollama_ask(prompt, model=model)


def ai_patterns(entries, model="llama3"):
    """
    Ask the local AI to find patterns across multiple entries.
    Returns response text, or None if AI is unavailable.
    """
    if not _ollama_available():
        return None

    combined = "\n\n---\n\n".join(
        f"[{_format_moment(e['moment'])}]\n{e['text']}"
        for e in entries[-10:]  # Last 10 entries max
    )

    prompt = f"""You are a thoughtful, private journal companion.
Here are several diary entries from one person:

{combined}

Identify 2-3 genuine patterns, recurring themes, or shifts you notice.
Be specific to what they wrote. Avoid generic observations.
Keep your response under 200 words."""

    return _ollama_ask(prompt, model=model)


# ─────────────────────────────────────────────────────────
# INTERACTIVE COMMANDS
# ─────────────────────────────────────────────────────────

def cmd_write(store):
    """Write a new diary entry."""
    print("\n ┌──────────────────────────────────────────────────────┐")
    print(" │  NEW ENTRY                                           │")
    print(" │  Write freely. Press Enter twice when done.         │")
    print(" │  (or type a single '.' on a line to finish)         │")
    print(" └──────────────────────────────────────────────────────┘\n")

    lines = []
    print(" > ", end="", flush=True)
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == ".":
            break
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
        if line != "":
            print(" > ", end="", flush=True)

    text = "\n".join(lines).strip()
    if not text:
        print("\n Nothing written.\n")
        return

    # Optional mood
    print()
    mood = input(" Mood (optional, Enter to skip): ").strip()

    # Optional tags
    tags_input = input(" Tags (space-separated, Enter to skip): ").strip()
    tags = [t.lstrip("#") for t in tags_input.split() if t] if tags_input else []

    try:
        entry = make_entry(text, tags=tags, mood=mood)
        store.save(entry)

        print(f"\n ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f" Entry saved. {store.count()} total.")
        print(f" Stamp: {entry['stamp'][:32]}...")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    except ValueError as e:
        print(f"\n {e}\n")


def cmd_read(store, n=5):
    """Show recent entries."""
    entries = store.recent(n)
    if not entries:
        print("\n No entries yet. Write something: --write\n")
        return

    total = store.count()
    print(f"\n Last {len(entries)} of {total} entries:")

    for i, entry in enumerate(reversed(entries), 1):
        _print_entry(entry, index=total - i + 1, short=True)


def cmd_view(store, index):
    """View a single entry in full."""
    entries = store.load()
    if not entries:
        print("\n No entries.\n")
        return

    try:
        idx = int(index) - 1
        if idx < 0 or idx >= len(entries):
            print(f"\n Entry {index} not found. You have {len(entries)} entries.\n")
            return
        _print_entry(entries[idx], index=int(index), short=False)
    except ValueError:
        print(f"\n Invalid index: {index}\n")


def cmd_search(store, query):
    """Search entries by text, tag, or mood."""
    results = store.search(query)
    if not results:
        print(f"\n No entries found for: '{query}'\n")
        return

    entries = store.load()
    print(f"\n {len(results)} entry/entries found for '{query}':\n")
    for entry in results:
        idx = entries.index(entry) + 1
        _print_entry(entry, index=idx, short=True)


def cmd_today(store):
    """Show today's entries."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = store.by_date(today)

    if not entries:
        print(f"\n No entries today ({today}).\n")
        return

    all_entries = store.load()
    print(f"\n {len(entries)} entry/entries today ({today}):\n")
    for entry in entries:
        idx = all_entries.index(entry) + 1
        _print_entry(entry, index=idx, short=False)


def cmd_stats(store):
    """Show diary statistics."""
    entries = store.load()
    valid, tampered = store.integrity_check()

    print(f"\n DIARY — v{DIARY_VERSION}")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Entries:   {len(entries)}")
    print(f" Verified:  {valid} ✓")
    if tampered:
        print(f" Modified:  {len(tampered)} ✗")
        for m in tampered:
            print(f"   - {m}")
    print(f" Encrypted: {'yes' if store.key else 'no'}")

    if entries:
        first = _format_moment(entries[0]["moment"])
        last  = _format_moment(entries[-1]["moment"])
        print(f" First:     {first}")
        print(f" Last:      {last}")

        # Count moods
        moods = [e["mood"] for e in entries if e.get("mood")]
        if moods:
            from collections import Counter
            top = Counter(moods).most_common(3)
            print(f" Moods:     {', '.join(f'{m}({c})' for m, c in top)}")

        # Count tags
        all_tags = [t for e in entries for t in e.get("tags", [])]
        if all_tags:
            from collections import Counter
            top_tags = Counter(all_tags).most_common(5)
            print(f" Tags:      {', '.join(f'#{t}({c})' for t, c in top_tags)}")

        # Word count
        total_words = sum(len(e["text"].split()) for e in entries)
        print(f" Words:     {total_words:,}")

    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def cmd_ai_reflect(store, index=None, model="llama3"):
    """Ask the local AI to reflect on an entry."""
    if not _ollama_available():
        print("\n ┌──────────────────────────────────────────────────────┐")
        print(" │  AI NOT AVAILABLE                                    │")
        print(" │                                                      │")
        print(" │  Ollama is not running.                              │")
        print(" │                                                      │")
        print(" │  To enable local AI:                                 │")
        print(" │    1. Install Ollama: https://ollama.com             │")
        print(" │    2. Run: ollama pull llama3                        │")
        print(" │    3. Run: ollama serve                              │")
        print(" │                                                      │")
        print(" │  Your diary works without it.                       │")
        print(" └──────────────────────────────────────────────────────┘\n")
        return

    entries = store.load()
    if not entries:
        print("\n No entries to reflect on.\n")
        return

    if index is not None:
        try:
            entry = entries[int(index) - 1]
        except (ValueError, IndexError):
            print(f"\n Entry {index} not found.\n")
            return
    else:
        entry = entries[-1]  # Most recent

    _print_entry(entry, short=True)
    print(" Thinking...\n")

    response = ai_reflect(entry, model=model)
    if response:
        print(f" ┌──────────────────────────────────────────────────────┐")
        print(f" │  AI REFLECTION                                       │")
        print(f" └──────────────────────────────────────────────────────┘\n")
        print(_wrap(response, width=68, indent=" "))
        print()
    else:
        print(" AI did not respond. Is Ollama running?\n")


def cmd_ai_patterns(store, model="llama3"):
    """Ask the local AI to find patterns across recent entries."""
    if not _ollama_available():
        print("\n AI not available. Run: ollama serve\n")
        return

    entries = store.recent(10)
    if len(entries) < 2:
        print("\n Need at least 2 entries to find patterns.\n")
        return

    print(f" Analyzing {len(entries)} entries...\n")
    response = ai_patterns(entries, model=model)
    if response:
        print(f" ┌──────────────────────────────────────────────────────┐")
        print(f" │  PATTERNS                                            │")
        print(f" └──────────────────────────────────────────────────────┘\n")
        print(_wrap(response, width=68, indent=" "))
        print()
    else:
        print(" AI did not respond.\n")


# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

def main():
    print(f"\n PHANTOM DIARY — v{DIARY_VERSION}")
    print(" Your thoughts belong to you.\n")

    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(" Usage:")
        print("   --write              write a new entry")
        print("   --read               see your last 5 entries")
        print("   --read <n>           see your last n entries")
        print("   --view <n>           read entry number n in full")
        print("   --today              see today's entries")
        print("   --search <query>     search entries by text, tag, or mood")
        print("   --stats              diary statistics")
        print("   --verify             check all entries for tampering")
        print()
        print(" AI (requires Ollama running locally):")
        print("   --reflect            AI reflects on your latest entry")
        print("   --reflect <n>        AI reflects on entry n")
        print("   --patterns           AI finds patterns in recent entries")
        print("   --model <name>       use a specific Ollama model (default: llama3)")
        print()
        print(" Writing tips:")
        print("   Press Enter twice to finish an entry")
        print("   Or type a single '.' on a line")
        print()
        return

    km = KeyManager()
    km.init_encryption()
    store = DiaryStore(km)

    model = "llama3"
    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args):
            model = args[idx + 1]

    if "--write" in args or "-w" in args:
        cmd_write(store)

    elif "--read" in args or "-r" in args:
        n = 5
        idx = args.index("--read") if "--read" in args else args.index("-r")
        if idx + 1 < len(args):
            try:
                n = int(args[idx + 1])
            except ValueError:
                pass
        cmd_read(store, n)

    elif "--view" in args:
        idx = args.index("--view")
        if idx + 1 < len(args):
            cmd_view(store, args[idx + 1])
        else:
            print(" Usage: --view <entry number>")

    elif "--today" in args:
        cmd_today(store)

    elif "--search" in args:
        idx = args.index("--search")
        if idx + 1 < len(args):
            query = " ".join(args[idx + 1:])
            cmd_search(store, query)
        else:
            print(" Usage: --search <query>")

    elif "--stats" in args:
        cmd_stats(store)

    elif "--verify" in args:
        valid, tampered = store.integrity_check()
        total = store.count()
        print(f"\n {valid}/{total} entries verified intact.")
        if tampered:
            print(f" {len(tampered)} entry/entries were modified after writing:")
            for m in tampered:
                print(f"   - {m}")
        else:
            print(" No tampering detected.\n")

    elif "--reflect" in args:
        idx = args.index("--reflect")
        index = None
        if idx + 1 < len(args):
            try:
                index = int(args[idx + 1])
            except ValueError:
                pass
        cmd_ai_reflect(store, index=index, model=model)

    elif "--patterns" in args:
        cmd_ai_patterns(store, model=model)

    else:
        # Default: show recent entries, or prompt to write
        count = store.count()
        if count == 0:
            print(" No entries yet.")
            print(" Start writing: python phantom_diary.py --write\n")
        else:
            cmd_read(store, n=5)


if __name__ == "__main__":
    main()
