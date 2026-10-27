"""Loads the YAML policy and turns it into ready-to-run pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.core.errors import PolicyError
from app.core.pipeline import GuardPipeline
from app.core.registry import get_guard_class
from app.core.types import Action, FailMode, Stage


class GuardSpec(BaseModel):
    type: str
    action: Action = Action.BLOCK
    fail_mode: FailMode = FailMode.CLOSED
    timeout_s: float = 2.0
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class Policy(BaseModel):
    version: int = 1
    scan_roles: list[str] = Field(default_factory=lambda: ["user"])
    restore_pii_in_output: bool = True
    input: list[GuardSpec] = Field(default_factory=list)
    output: list[GuardSpec] = Field(default_factory=list)


def load_policy(path: str | Path) -> Policy:
    path = Path(path)
    if not path.exists():
        raise PolicyError(f"Policy file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
        return Policy.model_validate(raw)
    except (yaml.YAMLError, ValidationError) as exc:
        raise PolicyError(f"Invalid policy file {path}: {exc}") from exc


def build_pipeline(specs: list[GuardSpec], stage: Stage) -> GuardPipeline:
    guards = []
    for spec in specs:
        if not spec.enabled:
            continue
        cls = get_guard_class(spec.type)
        guards.append(
            cls(action=spec.action, fail_mode=spec.fail_mode, timeout_s=spec.timeout_s, **spec.params)
        )
    return GuardPipeline(guards, stage)
