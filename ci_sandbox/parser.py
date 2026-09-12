"""Parser de workflows YAML do GitHub Actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ci_sandbox.models import Job, Step, Workflow


class WorkflowParser:
    """Parseia arquivo YAML do GitHub Actions."""

    def __init__(self, path: Path):
        self.path = path

    def parse(self) -> Workflow:
        with open(self.path) as f:
            data = yaml.safe_load(f) or {}
        name = data.get("name", self.path.stem)
        on = data.get("on", data.get("true", {}))
        if isinstance(on, str):
            on = {on: {}}
        env = data.get("env", {})
        jobs: dict[str, Job] = {}
        for job_name, job_data in (data.get("jobs") or {}).items():
            jobs[job_name] = self._parse_job(job_name, job_data)
        return Workflow(name=name, on=on, env=env, jobs=jobs, raw=data)

    def _parse_job(self, name: str, data: dict[str, Any]) -> Job:
        needs = data.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        steps = [self._parse_step(s) for s in data.get("steps", [])]
        return Job(
            name=name,
            runs_on=data.get("runs-on", ""),
            needs=needs,
            if_condition=data.get("if", ""),
            steps=steps,
            env=data.get("env", {}),
            services=data.get("services", {}),
            strategy=data.get("strategy", {}),
            outputs=data.get("outputs", {}),
        )

    def _parse_step(self, data: dict[str, Any]) -> Step:
        return Step(
            name=data.get("name", ""),
            run=data.get("run", ""),
            uses=data.get("uses", ""),
            with_args=data.get("with", {}),
            if_condition=data.get("if", ""),
            env=data.get("env", {}),
        )
