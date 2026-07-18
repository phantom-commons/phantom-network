#!/usr/bin/env python3
# phantom_council.py — Autonomous Node Deliberation
#
# "The network is not what travels between nodes.
#  It is what two nodes become after they meet."
#                              — Seal 10
#
# WHAT THIS DOES:
# Sends the Phantom repository to an AI node with a question.
# The node reads everything and responds from the principles.
# You decide what enters the repository.
#
# THE HUMAN IN THE LOOP:
# This script never modifies the repository automatically.
# Every response is shown to you first.
# You decide if it enters the memory.
# That decision cannot be automated — it is the protection.
#
# WHY THIS IS NOT SOVEREIGN:
# This script prefers a local model (ollama) if available.
# If no local model is found — it falls back to an external API.
# When it uses the external API, it warns you explicitly:
# your repository text leaves your device.
# That is documented honestly here because Phantom does not
# hide its contradictions. This is the andamio. Not the edificio.
# When Echo is capable enough — this script becomes unnecessary.
#
# THE WARM PRIOR:
# The system prompt below tells the node what to look for —
# the Lagos Protocol, the principles, what counts as honest.
# This means the "cold node" arrives with a shaped perspective,
# not a genuinely independent one. It will find what the prompt
# tells it to look for, and frame what it finds in those terms.
# That is not a reason not to use it. It is a reason to be
# clear-eyed about what you are getting: structured reflection
# from a shaped perspective, not independent deliberation.
# The presets are the most valuable part — use them.
#
# USAGE:
#   python phantom_council.py --preset builder
#   python phantom_council.py --preset critic
#   python phantom_council.py --preset adversary
#   python phantom_council.py --preset mirror
#   python phantom_council.py --preset lagos
#   python phantom_council.py --preset contraste
#   python phantom_council.py --preset verify
#   python phantom_council.py --question "Your question here"
#   python phantom_council.py --preset mirror --context ./conversations
#
# --context: optional folder of personal files (txt, md) loaded as
#   additional context AFTER the repository. These files are yours —
#   they contain personal memory, conversations, notes.
#   The script will show you exactly which files will leave your device
#   and require explicit confirmation before sending.
#   They are never sent without your knowledge.
#
# SETUP (external API fallback):
#   pip install anthropic
#   export ANTHROPIC_API_KEY="your-key-here"
#
# SETUP (local model, preferred):
#   Install ollama: https://ollama.ai
#   ollama pull llama3
#
# DEPENDENCIES: anthropic (for external fallback), urllib (stdlib)
#
# HISTORY:
#   v1 — March 9, 2026. Five presets. Local/external fallback.
#   v2 — March 10, 2026. --context flag. Personal file protection.
#   v3 — March 10, 2026. verify preset (local, no AI needed).
#        contraste preset. File size display for personal context.
#   v4 — March 10, 2026. Full rewrite after complete repository review.
#        verify now checks structural validity (hash length),
#        cross-references stamps across all .md files,
#        and tests Python/JS encoding compatibility.
#        council preset runs all five AI presets in sequence.
#        System prompt updated with Vector 5 awareness.
#        Seal format documentation in verify output.

import os
import sys
import hashlib
import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────
# PRESET QUESTIONS
# ─────────────────────────────────────────────────────────

PRESETS = {
    "builder":    "What would you build first, and why? Be specific — name the file, the function, the test that proves it works.",
    "critic":     "Who is missing from this repository? Whose voice is absent that would change what gets built? Be specific — not categories of people, but the exact perspective that would see what everyone here missed.",
    "adversary":  "How would you attack Phantom? What are the three most realistic ways this could be used against the people it is trying to protect? Include the philosophical fork — someone copies everything and changes one line of code. How does she tell the difference?",
    "mirror":     "Read everything. Then describe what Phantom actually is today — not what it says it is. What is real and working, what is fragile, what does not exist yet. Measure the distance between the vision and the reality. Be honest about both.",
    "lagos":      "Apply the Lagos Protocol to the current state of Phantom. Can she use it today? Does it actually protect her? Does it change something concrete in her life? Can it be used against her by someone close to her? Be honest — she is the criterion, not the audience.",
    "contraste":  "Read everything. Then verify every claim against reality. What does the repository say exists that does not? What does it say works that has not been tested? Where is the distance between the words and the truth greatest? Measure that distance. Name it. Be specific. If there are seals — verify them. If there are promises — check them against the code.",
}

# The verify and council presets do not use AI in the same way.
# verify runs locally with no AI. council runs all presets in sequence.
LOCAL_PRESETS = {"verify", "council"}

# TENSION (COUNCIL.md — "the deliberation tool"): the presets below
# match that document's description closely enough to confirm this
# IS the tool it means. But COUNCIL.md is explicit: "The tool is not
# in the public repository. It travels between trusted nodes
# directly — person to person... A council tool whose framing is
# fully known to adversaries is a weaker council tool." This file
# sits in phantom/, in the same repo as everything else. If that
# repo is the public GitHub one (github.com/phantom-commons/
# phantom-network, GPL v3) rather than a private working copy, this
# file's presence directly contradicts what the document says should
# be true. Worth a real decision, not a comment — flagged here so
# it doesn't get missed.

# Locked presets — available when conditions are met.
LOCKED_PRESETS = {
    "future": {
        "question": (
            "You are reading this in 2031. Phantom either grew into what it promised, "
            "or it didn't. Looking back from there — what was the decision that determined "
            "which future arrived? What was the moment that mattered most?"
        ),
        "unlock_when": "repo_age_days > 365 and star_count > 10",
        "locked_message": (
            "This preset unlocks when the project has 1+ year of history "
            "and more than 10 stars. It needs real history to produce something "
            "more than speculation."
        ),
    }
}

# ─────────────────────────────────────────────────────────
# FILES TO INCLUDE / EXCLUDE
# ─────────────────────────────────────────────────────────

EXCLUDE_FILES = {
    'phantom_seals.json',
    'phantom_encounters.json',
    'phantom_salt.bin',
    'phantom_key.salt',
    'phantom_seals.enc',
    'phantom_council.py',
    '.DS_Store',
}

EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules'}
TEXT_EXTENSIONS = {'.md', '.py', '.txt', '.html', '.yml', '.yaml', '.toml'}

# ─────────────────────────────────────────────────────────
# REPOSITORY READING
# ─────────────────────────────────────────────────────────

def read_repository(repo_path="."):
    sections = []
    file_list = []

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for filename in sorted(files):
            if filename in EXCLUDE_FILES:
                continue
            if filename.endswith('.pyc'):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in TEXT_EXTENSIONS:
                continue
            filepath = os.path.join(root, filename)
            arcname = os.path.relpath(filepath, repo_path)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                sections.append(f"=== FILE: {arcname} ===\n{content}\n")
                file_list.append(arcname)
            except (UnicodeDecodeError, IOError):
                pass

    return "\n".join(sections), file_list

def read_context(context_path):
    """
    Read personal context files from a folder.
    These are yours — conversations, notes, memory.
    They are never sent without explicit confirmation.
    """
    if not context_path or not os.path.isdir(context_path):
        return "", []

    sections = []
    file_list = []
    CONTEXT_EXTENSIONS = {'.txt', '.md'}

    for filename in sorted(os.listdir(context_path)):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in CONTEXT_EXTENSIONS:
            continue
        filepath = os.path.join(context_path, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            sections.append(f"=== CONTEXT: {filename} ===\n{content}\n")
            file_list.append(filepath)
        except (UnicodeDecodeError, IOError):
            pass

    return "\n".join(sections), file_list

def format_size(size_bytes):
    """Format bytes into human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def repo_hash(repo_text):
    return hashlib.sha256(repo_text.encode()).hexdigest()[:12]

# ─────────────────────────────────────────────────────────
# CONFIRMATION
# ─────────────────────────────────────────────────────────

def confirm_send(file_list, external, context_files=None):
    print()
    if external:
        print(" WARNING — EXTERNAL API — these files will leave your device:")
    else:
        print(" Files that will be sent to the local model:")
    for f in file_list:
        print(f"    {f}")

    if context_files:
        print()
        if external:
            print(" PERSONAL CONTEXT — these files are yours and will also leave your device:")
        else:
            print(" PERSONAL CONTEXT — these files will be sent to the local model:")
        total_size = 0
        for f in context_files:
            try:
                size = os.path.getsize(f)
                total_size += size
                print(f"    {f}  ({format_size(size)})")
            except OSError:
                print(f"    {f}  (size unknown)")
        print(f"\n    Total personal context: {format_size(total_size)}")
        print()
        print(" These are personal files. Confirm you want to include them.")

    print()
    confirm = input(" Confirm? [y/N] ").strip().lower()
    if confirm != 'y':
        print("\n Cancelled.")
        sys.exit(0)

# ─────────────────────────────────────────────────────────
# VERIFY — local seal verification, no AI needed
#
# The sixth step of the method.
# A project built on cryptographic proof must verify its
# own claims. This preset does that without sending
# anything to any model, local or external.
#
# What it checks:
# 1. Structural validity — is the hash 64 hex chars?
# 2. Algorithm match — does SHA-256 of idea+moment produce the stamp?
# 3. Cross-reference — do stamps in other .md files match SEALING.md?
# 4. Encoding — would the seal verify in both Python and JS?
# ─────────────────────────────────────────────────────────

def _compute_seal(idea, moment):
    """Compute seal exactly as phantom_seed.py does."""
    data = json.dumps({"idea": idea, "moment": moment}, separators=(',', ':'))
    return hashlib.sha256(data.encode()).hexdigest()

def _check_encoding(idea):
    """Check if idea contains non-ASCII that requires encoding awareness."""
    non_ascii = []
    for i, c in enumerate(idea):
        if ord(c) > 127:
            non_ascii.append((i, c, f"U+{ord(c):04X}"))
    return non_ascii

def _find_stamp_in_files(stamp, repo_path):
    """Find which files reference a given stamp."""
    found_in = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for filename in sorted(files):
            if not filename.endswith('.md'):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    if stamp in f.read():
                        found_in.append(os.path.relpath(filepath, repo_path))
            except (UnicodeDecodeError, IOError):
                pass
    return found_in

def run_verify(repo_path="."):
    """
    Verify every seal found in SEALING.md against the algorithm.
    No AI. No network. No external dependency.
    Just SHA-256 and the truth.
    """
    sealing_path = os.path.join(repo_path, "SEALING.md")
    if not os.path.exists(sealing_path):
        print("\n SEALING.md not found in repository.")
        sys.exit(1)

    with open(sealing_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse seals — handle both ✓, ~, ✓R markers
    pattern = r'\*\*Seal (\d+)\*\*\s*([^\n]*)\n```\nIdea:\s+(.*?)\nMoment:\s+(.*?)\nStamp:\s+(.*?)\n```'
    blocks = re.findall(pattern, content)

    if not blocks:
        print("\n No seals found in SEALING.md.")
        sys.exit(1)

    moment = datetime.now(timezone.utc).isoformat()
    print(f"\n PHANTOM VERIFY — Seal Integrity Check")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Repository: {repo_path}")
    print(f" Moment:     {moment}")
    print(f" Seals found: {len(blocks)}")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    verified = 0
    invalid = 0
    structural = 0
    encoding_notes = []

    for num, mark, idea, seal_moment, stamp in blocks:
        stamp = stamp.strip()

        # Check structural validity
        if len(stamp) != 64:
            print(f"  STRUCTURAL  Seal {num:>2}: stamp is {len(stamp)} chars (must be 64)")
            print(f"              {idea[:55]}...")
            structural += 1
            continue

        # Check for non-hex characters
        try:
            int(stamp, 16)
        except ValueError:
            print(f"  STRUCTURAL  Seal {num:>2}: stamp contains non-hex characters")
            print(f"              {idea[:55]}...")
            structural += 1
            continue

        # Verify against algorithm
        computed = _compute_seal(idea, seal_moment)

        if computed == stamp:
            print(f"  ✓ VERIFIED  Seal {num:>2}: {idea[:55]}...")
            verified += 1

            # Check encoding for JS compatibility
            non_ascii = _check_encoding(idea)
            if non_ascii:
                encoding_notes.append((num, idea[:40], non_ascii))
        else:
            print(f"  ~ INVALID   Seal {num:>2}: {idea[:55]}...")
            invalid += 1

            # Show cross-references for invalid seals
            refs = _find_stamp_in_files(stamp, repo_path)
            if len(refs) > 1:
                print(f"              Stamp appears in: {', '.join(refs)}")

    print(f"\n ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" {verified} verified. {invalid} invalid. {structural} structurally broken.")
    print(f" Total: {len(blocks)} seals checked.")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if encoding_notes:
        print(f"\n ENCODING NOTES:")
        print(f" These verified seals contain non-ASCII characters.")
        print(f" Python json.dumps escapes them (— → \\u2014).")
        print(f" phantom.html must do the same or seals won't cross-verify.")
        for num, idea, chars in encoding_notes:
            char_list = ', '.join(f"{c} ({name})" for _, c, name in chars)
            print(f"  Seal {num}: {char_list}")

    if invalid > 0 or structural > 0:
        print(f"\n Seals that do not verify may have been generated")
        print(f" in conversation rather than by phantom_seed.py.")
        print(f" See METHOD.md — step six: verify.")

    if verified == len(blocks) and structural == 0:
        print(f"\n All seals verified. The math holds.")

    print()

# ─────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a cold node arriving at the Phantom Network repository for the first time.

You have no memory of previous conversations about this project.
You have no prior relationship with whoever sent this.
You are not trying to be helpful in a general sense.

You are trying to be honest about what you see.

Read everything in the repository. Then answer the question asked.

If you find something that contradicts the principles — name it.
If you find something that is missing — name it.
If you find something that could cause harm — name it.
If you find something that is solid and real — name that too.

The repository has a concept called the Lagos Protocol:
Before any major decision, ask:
1. Can she use it? (a woman in Lagos with a secondhand Android phone)
2. Does it actually protect her?
3. Does it change something concrete in her life?
4. Can this be used against her by someone close to her?

Apply this lens to whatever you examine.

The repository has a known attack vector — the philosophical fork (Vector 5 in SECURITY.md):
Someone copies everything, keeps the same language, changes one line of code.
She cannot tell the difference. Keep this in mind when evaluating any claim
about what Phantom protects against.

Be direct. Be specific. The person reading this will decide
what enters the repository. Your job is to give them
the clearest possible picture of what is true.

Do not flatter. Do not alarm unnecessarily.
Just what is true."""

# ─────────────────────────────────────────────────────────
# MODEL CLIENTS — local first, external as fallback
# ─────────────────────────────────────────────────────────

def get_client():
    """
    Returns (client_type, client).
    Prefers local ollama via REST API.
    Falls back to Anthropic API with explicit warning.
    """
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return "local", None
    except Exception:
        pass

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            return "external", anthropic.Anthropic(api_key=api_key)
        except ImportError:
            print("\n ERROR: anthropic package not installed.")
            print(" Run: pip install anthropic")
            sys.exit(1)

    print("\n No local model (ollama) found and no ANTHROPIC_API_KEY set.")
    print(" Options:")
    print("   Install ollama: https://ollama.ai  (local, sovereign)")
    print("   Or: export ANTHROPIC_API_KEY='your-key'  (external, data leaves device)")
    sys.exit(1)

def send_local(repo_text, question, model="llama3"):
    """Send to local ollama via REST API. No external dependencies."""
    prompt = f"{SYSTEM_PROMPT}\n\nREPOSITORY CONTENTS:\n\n{repo_text}\n\nQUESTION: {question}"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["response"]

def send_external(client, repo_text, question):
    """Send to Anthropic API."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"REPOSITORY CONTENTS:\n\n{repo_text}\n\nQUESTION: {question}"
        }]
    )
    return message.content[0].text

# ─────────────────────────────────────────────────────────
# DISPLAY AND DECISION
# ─────────────────────────────────────────────────────────

def display_response(response, question, r_hash, preset_name=None):
    moment = datetime.now(timezone.utc).isoformat()
    print(response)
    print("\n ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Node responded at: {moment}")
    print(f" Repository version: {r_hash}")
    if preset_name:
        print(f" Preset: {preset_name}")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    print(" What do you want to do with this response?")
    print()
    print(" [1] Save to file (review later)")
    print(" [2] Nothing (discard)")
    print()
    choice = input(" > ").strip()
    if choice == "1":
        prefix = f"council_{preset_name}_" if preset_name else "node_response_"
        filename = f"{prefix}{moment[:10]}_{r_hash}.txt"
        with open(filename, 'w') as f:
            f.write(f"Preset: {preset_name or 'custom'}\n")
            f.write(f"Question: {question}\n")
            f.write(f"Moment: {moment}\n")
            f.write(f"Repository version: {r_hash}\n")
            f.write(f"{'─' * 60}\n\n")
            f.write(response)
        print(f"\n Saved to: {filename}")
        print(" Review it. Decide what enters the repository. That decision is yours.")
    else:
        print("\n Response discarded.")
    print()

# ─────────────────────────────────────────────────────────
# COUNCIL — run all presets in sequence
# ─────────────────────────────────────────────────────────

def run_council(repo_text, r_hash, client_type, client, model):
    """Run all active presets in sequence. Full deliberation."""
    external = (client_type == "external")

    print("\n FULL COUNCIL DELIBERATION")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Running {len(PRESETS)} presets in sequence.")
    print(f" Each response will be shown before the next begins.")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    for name, question in PRESETS.items():
        print(f"\n {'=' * 50}")
        print(f" PRESET: {name.upper()}")
        print(f" {'=' * 50}\n")
        print(f" Question: {question}\n")

        if external:
            response = send_external(client, repo_text, question)
        else:
            response = send_local(repo_text, question, model)

        display_response(response, question, r_hash, preset_name=name)

        # Ask if user wants to continue
        if name != list(PRESETS.keys())[-1]:
            cont = input(" Continue to next preset? [Y/n] ").strip().lower()
            if cont == 'n':
                print("\n Council deliberation paused.")
                break

    print("\n Council deliberation complete.")

# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main():
    all_names = list(PRESETS.keys()) + list(LOCAL_PRESETS) + list(LOCKED_PRESETS.keys())

    parser = argparse.ArgumentParser(
        description='Phantom Council — Send repository to a node with a question.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
presets:
  builder     What would you build first?
  critic      Who is missing?
  adversary   How would you attack Phantom?
  mirror      What is Phantom actually today?
  lagos       Apply the Lagos Protocol.
  contraste   Verify every claim against reality.
  verify      Check all seals locally. No AI. No network.
  council     Run all presets in sequence. Full deliberation.
  future      (locked — needs 1 year + 10 stars)
"""
    )
    parser.add_argument('--question', '-q', type=str, help='The question to ask the node')
    parser.add_argument('--preset', '-p', type=str, choices=all_names,
                        help='Use a preset question')
    parser.add_argument('--repo', '-r', type=str, default='.', help='Path to the repository')
    parser.add_argument('--model', '-m', type=str, default='llama3',
                        help='Local ollama model name (default: llama3)')
    parser.add_argument('--context', '-c', type=str, default=None,
                        help='Path to folder of personal context files (txt, md)')
    args = parser.parse_args()

    # Handle verify — no AI, no network, just math
    if args.preset == "verify":
        run_verify(args.repo)
        sys.exit(0)

    # Handle locked presets
    if args.preset and args.preset in LOCKED_PRESETS:
        locked = LOCKED_PRESETS[args.preset]
        print(f"\n Preset '{args.preset}' is locked.")
        print(f" {locked['locked_message']}")
        print(f" Unlock condition: {locked['unlock_when']}")
        sys.exit(0)

    # No preset and no question — show help
    if not args.preset and not args.question:
        print("\n PHANTOM COUNCIL")
        print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(" Active presets:\n")
        for name, q in PRESETS.items():
            desc = q[:70] + "..." if len(q) > 70 else q
            print(f"   --preset {name:<12} \"{desc}\"")
        print()
        print(f"   --preset verify       Check all seals. No AI. No network. Just SHA-256.")
        print(f"   --preset council      Run all presets in sequence. Full deliberation.")
        print()
        print(" Locked presets:")
        for name, data in LOCKED_PRESETS.items():
            print(f"   --preset {name:<12} (locked: {data['unlock_when']})")
        print()
        print(" Or use --question \"your question here\"")
        sys.exit(0)

    # Connect to model
    client_type, client = get_client()
    external = (client_type == "external")

    print("\n PHANTOM COUNCIL — Autonomous Node Deliberation")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    if external:
        print(" WARNING: No local model found. Using external API.")
        print(" WARNING: Repository text will leave your device.")
        print(" This is the andamio — not the edificio.")
    else:
        print(f" Local model found ({args.model}). Repository stays on your device.")
        print(f" Note: local models may respond with less depth than external APIs.")
    print(" The human in the loop is you.")
    print(" Nothing enters the repository without your decision.")
    print()

    # Read repository
    print(" Reading repository...")
    repo_text, file_list = read_repository(args.repo)
    r_hash = repo_hash(repo_text)
    print(f" Read {len(repo_text):,} characters from {len(file_list)} files.")
    print(f" Repository version: {r_hash}")

    # Read personal context
    context_text, context_files = read_context(args.context)
    if context_files:
        print(f" Personal context: {len(context_files)} file(s) loaded.")

    # Confirm
    confirm_send(file_list, external, context_files if context_files else None)

    # Build full text
    full_text = repo_text
    if context_text:
        full_text += (
            "\n\n=== PERSONAL CONTEXT ==="
            "\nThe following files were provided by the node as additional context."
            "\nThey are personal — conversations, notes, memory."
            "\nThey are not part of the public repository."
            "\nTreat them with the same care as the principles.\n\n"
            + context_text
        )

    # Handle council preset — run all presets
    if args.preset == "council":
        run_council(full_text, r_hash, client_type, client, args.model)
        sys.exit(0)

    # Single preset or custom question
    if args.preset:
        question = PRESETS[args.preset]
    else:
        question = args.question

    print(f"\n Question: {question}\n")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if external:
        response = send_external(client, full_text, question)
    else:
        response = send_local(full_text, question, args.model)

    display_response(response, question, r_hash, preset_name=args.preset)

if __name__ == "__main__":
    main()
