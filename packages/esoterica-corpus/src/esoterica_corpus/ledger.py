"""Which record claimed each input unit"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from esoterica_corpus.records import Entry, Record, Unit


class LedgerError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Claim:
    kind: str  # "content" | "structure"
    claim: str


def claim_of(record: Record) -> Claim:
    if isinstance(record, Entry):
        return Claim("content", f"{record.target}.{record.key}")
    return Claim("structure", record.claim)


class Ledger:
    def __init__(self) -> None:
        self.by_unit: dict[Unit, Claim] = {}

    @classmethod
    def of(cls, records: Iterable[Record]) -> Ledger:
        ledger = cls()
        for record in records:
            ledger.add(record)
        return ledger

    def add(self, record: Record) -> None:
        claim = claim_of(record)
        if not record.units:
            raise LedgerError(f"{claim.claim!r} claims no input unit")
        for unit in record.units:
            if unit in self.by_unit:
                raise LedgerError(
                    f"input unit {unit!r} claimed twice: "
                    f"{self.by_unit[unit].claim!r} and {claim.claim!r}"
                )
            self.by_unit[unit] = claim

    def __contains__(self, unit: Unit) -> bool:
        return unit in self.by_unit

    def __len__(self) -> int:
        return len(self.by_unit)
