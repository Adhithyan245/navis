"""
Workflow definition file loader. Supports YAML and JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml


class LoaderError(Exception):
    pass


def load_definition(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise LoaderError(f"workflow definition not found: {p}")
    text = p.read_text(encoding="utf-8")

    suffix = p.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise LoaderError(f"failed to parse YAML {p}: {e}") from e
    elif suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LoaderError(f"failed to parse JSON {p}: {e}") from e
    else:
        raise LoaderError(f"unsupported workflow format {suffix!r} for {p}")

    if not isinstance(data, dict):
        raise LoaderError(f"workflow {p} must be a mapping at the top level")
    return data
