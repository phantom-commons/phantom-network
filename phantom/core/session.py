"""
session.py — PhantomSession

Una passphrase. Una identidad. Todo el nodo.
Va en la misma carpeta que phantom_core.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from phantom_core import (
    KeyManager, SealStore, EncounterLog, PulseLedger,
    ContactBook, DMStore, PHANTOM_VERSION,
)
from phantom_diary import DiaryStore


@dataclass
class PhantomSession:
    km:            KeyManager
    identity:      object          # NodeIdentity
    store:         SealStore
    encounter_log: EncounterLog
    pulse_ledger:  PulseLedger
    contact_book:  ContactBook
    dm_store:      DMStore
    diary_store:   DiaryStore
    wallet:        Optional[object] = field(default=None, repr=False)

    @property
    def version(self) -> str:
        return PHANTOM_VERSION

    @property
    def node_name(self) -> str:
        if self.identity and self.identity.node_name:
            return self.identity.node_name
        return "(sin nombre)"

    @property
    def fingerprint(self) -> str:
        return self.identity.fingerprint if self.identity else "—"

    @property
    def fingerprint_short(self) -> str:
        fp = self.fingerprint
        return fp[:8] + "..." if len(fp) > 8 else fp

    @property
    def encrypted(self) -> bool:
        return self.km.has_key

    @classmethod
    def open(cls, km: KeyManager) -> "PhantomSession":
        """Abre la sesion desde un KeyManager ya desbloqueado."""
        import phantom_node
        identity = phantom_node._load_or_create_identity(km)
        identity = phantom_node._ensure_dm_ready(identity, km)
        return cls(
            km=km,
            identity=identity,
            store=SealStore(km),
            encounter_log=EncounterLog(km),
            pulse_ledger=PulseLedger(km),
            contact_book=ContactBook(km),
            dm_store=DMStore(km),
            diary_store=DiaryStore(km),
        )

    def summary(self) -> dict:
        import io, contextlib
        _sink = io.StringIO()
        with contextlib.redirect_stdout(_sink), contextlib.redirect_stderr(_sink):
            try:    seals = self.store.count()
            except: seals = 0
            try:    encounters = len(self.encounter_log.load())
            except: encounters = 0
            try:    contacts = len(self.contact_book.all())
            except: contacts = 0
        return {
            "seals": seals,
            "encounters": encounters,
            "contacts": contacts,
            "encrypted": self.encrypted,
        }
