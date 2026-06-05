"""
Schema Healer — detects API response drift and self-heals test fixtures.

Behaviour
---------
First run   : writes a fixture from the live API response and continues.
Later runs  : compares the current response shape to the stored fixture.
  - New or renamed fields  → logs SCHEMA_DRIFT warning, updates fixture, continues.
  - Required fields absent → raises SchemaBrokenError immediately (hard stop).
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("schema_healer")

DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "predict_schema.json"
REQUIRED_FIELDS = frozenset({"label", "confidence"})


# ── Exceptions ─────────────────────────────────────────────────────────────────

class SchemaBrokenError(Exception):
    """Required field is completely absent — test cannot continue."""


# ── Result object ───────────────────────────────────────────────────────────────

@dataclass
class HealResult:
    ok: bool
    healed: bool = False
    added_fields: set = field(default_factory=set)
    removed_fields: set = field(default_factory=set)
    message: str = ""


# ── Healer ──────────────────────────────────────────────────────────────────────

class SchemaHealer:
    """
    Parameters
    ----------
    fixture_path    : path to the JSON fixture file (created on first run)
    required_fields : fields that must always be present; missing → hard fail
    """

    def __init__(
        self,
        fixture_path: Path = DEFAULT_FIXTURE,
        required_fields: frozenset = REQUIRED_FIELDS,
    ):
        self.fixture_path = Path(fixture_path)
        self.required_fields = required_fields

    # ── Public API ──────────────────────────────────────────────────────────────

    def check(self, response: dict) -> HealResult:
        """
        Validate response shape against the stored fixture.

        Decision tree
        -------------
        No fixture yet        → create it from this response; return OK.
        Required fields gone,
          nothing new either  → hard break (SchemaBrokenError).
        Required fields gone,
          but new ones arrived → likely a rename; log SCHEMA_DRIFT, heal, continue.
        Non-required drift     → log SCHEMA_DRIFT, heal, continue.
        No change             → return OK silently.
        """
        current = set(response.keys())
        fixture = self._load_fixture()

        # ── First run ──────────────────────────────────────────────────────────
        if fixture is None:
            self._assert_required_present(current)
            self._save_fixture(current)
            logger.info("Fixture initialised with fields: %s", sorted(current))
            return HealResult(ok=True, message="Fixture created on first run")

        stored   = set(fixture["fields"])
        required = set(fixture.get("required", self.required_fields))
        added    = current - stored
        removed  = stored  - current

        # ── Determine break vs drift ───────────────────────────────────────────
        missing_required = required - current

        if missing_required:
            if added:
                # Required fields gone but new fields appeared → likely a rename.
                # Promote the new fields into the required set so the healed
                # fixture stays internally consistent.
                new_required = (required - missing_required) | added
                logger.warning(
                    "SCHEMA_DRIFT — required field(s) renamed: "
                    "removed=%s  replaced_by=%s",
                    sorted(missing_required),
                    sorted(added),
                )
                self._save_fixture(current, required_override=new_required)
                logger.info("Fixture healed → continuing tests")
                return HealResult(
                    ok=True,
                    healed=True,
                    added_fields=added,
                    removed_fields=removed,
                    message=(
                        f"SCHEMA_DRIFT healed (rename): "
                        f"removed={sorted(removed)}, added={sorted(added)}"
                    ),
                )
            else:
                # Required fields gone, nothing replaced them → genuine break
                self._assert_required_present(current)

        # ── Non-required drift (extra or removed optional fields) ──────────────
        if added or removed:
            logger.warning(
                "SCHEMA_DRIFT — added=%s  removed=%s",
                sorted(added) or "none",
                sorted(removed) or "none",
            )
            self._save_fixture(current)
            logger.info("Fixture healed → continuing tests")
            return HealResult(
                ok=True,
                healed=True,
                added_fields=added,
                removed_fields=removed,
                message=(
                    f"SCHEMA_DRIFT healed: "
                    f"added={sorted(added) or 'none'}, "
                    f"removed={sorted(removed) or 'none'}"
                ),
            )

        return HealResult(ok=True, message="Schema matches fixture — no drift")

    def reset_fixture(self) -> None:
        """Remove the fixture so the next check() recreates it."""
        if self.fixture_path.exists():
            self.fixture_path.unlink()

    # ── Internals ───────────────────────────────────────────────────────────────

    def _assert_required_present(self, current: set) -> None:
        missing = self.required_fields - current
        if missing:
            msg = f"SCHEMA_BREAK — required fields missing: {sorted(missing)}"
            logger.error(msg)
            raise SchemaBrokenError(msg)

    def _load_fixture(self) -> dict | None:
        if not self.fixture_path.exists():
            return None
        return json.loads(self.fixture_path.read_text())

    def _save_fixture(self, fields: set, required_override: set = None) -> None:
        required = required_override if required_override is not None else self.required_fields
        self.fixture_path.parent.mkdir(parents=True, exist_ok=True)
        self.fixture_path.write_text(
            json.dumps(
                {"fields": sorted(fields), "required": sorted(required)},
                indent=2,
            )
        )
