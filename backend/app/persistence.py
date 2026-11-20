"""Save and load the household as JSON so it survives a restart.

Only the family's own data is written (see FamilyState.to_dict); settings and secrets never are.
The path comes from AANGAN_DATA_FILE (read on each call, so tests can redirect it), default backend/data/household.json.
"""

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("aangan.persistence")

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "household.json"
_write_lock = threading.Lock()


def data_path() -> Path:
    override = os.getenv("AANGAN_DATA_FILE", "").strip()
    return Path(override) if override else DEFAULT_PATH


def save(state) -> Path:
    """Write the household atomically: a temp file in the same folder, then replace."""
    path = data_path()
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, path)
    return path


def load(state) -> bool:
    """Load the saved household into `state`. Returns False when there is no usable file.
    A corrupt file is kept aside as `<name>.bad` and the state is left as it was."""
    path = data_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("saved household is not an object")
        state.apply_dict(data)
        return True
    except Exception as exc:  # corrupt JSON, wrong shape, unreadable file: never crash startup
        bad = path.with_name(path.name + ".bad")
        log.warning("could not load %s (%s); keeping it as %s and starting empty", path, exc, bad.name)
        try:
            os.replace(path, bad)
        except OSError:
            pass
        return False
