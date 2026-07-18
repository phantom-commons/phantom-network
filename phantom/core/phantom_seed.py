# phantom_seed.py — v0.5
#
# The seal tool of Phantom Network.
# Node Zero. March 8, 2026.
#
# Seal an idea. Verify a seal. Nothing else.
#
# WHY THIS FILE EXISTS:
# Human thought is sacred. Any system that touches it without
# permission violates something that has no price because it
# has no owner.
#
# To verify any seal (no software needed):
#   import hashlib, json
#   data = json.dumps({"idea":"...","moment":"..."}, separators=(',',':'))
#   print(hashlib.sha256(data.encode()).hexdigest())
#
# HISTORY:
#   v0.1 — March 8, 2026. Seal and verify. Genesis seals.
#   v0.2 — March 9, 2026. Three modes. Save to disk.
#   v0.3 — March 10, 2026. Encryption at rest (AES-256-GCM).
#   v0.5 — March 10, 2026. Unified on phantom_core.py.

from phantom_core import (
    seal, verify, KeyManager, SealStore,
    MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL,
)


def main():
    print("\n PHANTOM NETWORK — Seal Tool")
    print(" Privacy is not for hiding. It is for being free.\n")

    action = input(" [1] Seal an idea  [2] Verify a seal\n > ")

    if action == "1":
        km = KeyManager()
        km.init_encryption()
        store = SealStore(km)

        idea = input("\n Enter idea to seal:\n > ")

        print("""
 Before you seal — choose the mode:

 [1] PRIVATE    — Exists only on your device. Never propagated.
                  THIS IS THE DEFAULT — the safest option.

 [2] PERMANENT  — Exists forever. Goes into the public record.
                  Cannot be undone.

 [3] EPHEMERAL  — Travels but does not anchor. No permanent record.
""")
        mode = input(" Mode (Enter for PRIVATE):\n > ").strip()
        mode_labels = {"1": MODE_PRIVATE, "2": MODE_PERMANENT, "3": MODE_EPHEMERAL}
        mode_label = mode_labels.get(mode, MODE_PRIVATE)

        print(f"\n Mode selected: {mode_label}")
        if mode_label == MODE_PERMANENT:
            print(" This seal will exist forever. It belongs to the network.")
            confirm_permanent = input(" Are you sure? [y/n]\n > ").strip().lower()
            if confirm_permanent != "y":
                print(" Switched to private.\n")
                mode_label = MODE_PRIVATE

        confirm = input(" Seal this idea? [y/n]\n > ").strip().lower()
        if confirm == "y":
            try:
                entry = seal(idea, mode_label)
                print(f"\n PHANTOM SEAL")
                print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print(f" Idea:   {entry['idea']}")
                print(f" Moment: {entry['moment']}")
                print(f" Stamp:  {entry['stamp']}")
                print(f" Mode:   {entry['mode']}")
                print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                if store.save(entry):
                    count = store.count()
                    print(f" Saved — {count} seal(s) on this device.")
                else:
                    print(" (Duplicate — this seal already exists.)")
            except ValueError as e:
                print(f"\n {e}\n")
        else:
            print("\n Seal cancelled.\n")

    elif action == "2":
        idea = input("\n Idea:\n > ")
        moment = input(" Moment:\n > ")
        stamp = input(" Stamp:\n > ")
        if verify(idea, moment, stamp):
            print(f"\n SEAL VERIFIED — this idea existed, exactly as written.")
        else:
            print(f"\n SEAL INVALID — something was changed.")


if __name__ == "__main__":
    main()
