"""Modelos de dados para workflows CI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    name: str = ""
    run: str = ""
    uses: str = ""
    with_args: dict[str, str] = field(default_factory=dict)
    if_condition: str = ""
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Job:
    name: str
    runs_on: str = ""
    needs: list[str] = field(default_factory=list)
    if_condition: str = ""
    steps: list[Step] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    services: dict[str, Any] = field(default_factory=dict)
    strategy: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    # resolved at sim time
    status: str = "pending"  # pending | running | skipped | success | failure
    skipped_because: str = ""


@dataclass
class Workflow:
    name: str
    on: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
