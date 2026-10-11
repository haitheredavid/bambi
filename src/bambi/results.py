"""results.json: an append-only log of what happened to a print workspace.

bambi writes it; the modelling side reads it. `runs` record checks, slices, prints and coupon
picks. `recommendations` are changes bambi suggests to the model (a model.toml key or a builder
parameter). The model closes one by listing its id in [print] feedback_applied or
feedback_declined, which `blend print-pack` copies into the spec. Schema:
`bambi docs print-results`.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

FILE = "results.json"
SCHEMA = "print-results/1"
RUN_KINDS = ("check", "slice", "print", "fit")
OUTCOMES = ("ok", "failed", "partial")
FAILURES = (
    "sag",
    "warp",
    "adhesion",
    "stringing",
    "fit",
    "layer-shift",
    "snap",
    "spaghetti",
    "other",
)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Results:
    path: Path
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, directory: Path, model: str = "", pack: str = "") -> "Results":
        path = directory / FILE
        if path.exists():
            return cls(path, json.loads(path.read_text()))
        return cls(
            path,
            {
                "schema": SCHEMA,
                "model": model,
                "pack": pack,
                "runs": [],
                "recommendations": [],
            },
        )

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    @property
    def runs(self) -> list[dict]:
        return self.data.setdefault("runs", [])

    @property
    def recommendations(self) -> list[dict]:
        return self.data.setdefault("recommendations", [])

    def _id(self, prefix: str, existing: list[dict]) -> str:
        # Recommendations travel upstream, where several packs' ids meet in one model.toml.
        pack = Path(self.data.get("pack") or "").name
        if prefix == "rec" and pack and pack != "print":
            prefix = f"rec-{pack}"
        stamp = datetime.now().astimezone().strftime("%Y%m%d")
        n = sum(1 for r in existing if r.get("id", "").startswith(f"{prefix}-{stamp}"))
        return f"{prefix}-{stamp}-{n + 1:02d}"

    def add_run(self, kind: str, **fields) -> dict:
        if kind not in RUN_KINDS:
            raise ValueError(f"run kind must be one of {', '.join(RUN_KINDS)}")
        run = {"id": self._id(kind[:3], self.runs), "kind": kind, "at": now(), **fields}
        self.runs.append(run)
        return run

    def add_recommendation(
        self, target: str, value, reason: str, source: str = "", alt: str = ""
    ) -> dict:
        rec = {
            "id": self._id("rec", self.recommendations),
            "at": now(),
            "from": source,
            "target": target,
            "value": value,
            "reason": reason,
            **({"alt": alt} if alt else {}),
        }
        self.recommendations.append(rec)
        return rec

    def last(self, kind: str) -> dict | None:
        return next((r for r in reversed(self.runs) if r["kind"] == kind), None)

    def pending(self, closed: set[str]) -> list[dict]:
        return [r for r in self.recommendations if r["id"] not in closed]
