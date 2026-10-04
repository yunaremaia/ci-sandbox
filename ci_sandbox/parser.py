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
        if not isinstance(data, dict):
            raise ValueError(
                f"{self.path}: workflow root must be a mapping, "
                f"got {type(data).__name__}"
            )
        name = data.get("name", self.path.stem)
        on = self._parse_on(data)
        env = data.get("env", {})
        if not isinstance(env, dict):
            raise ValueError(
                f"{self.path}: 'env' must be a mapping, got {type(env).__name__}"
            )
        jobs_data = data.get("jobs") or {}
        if not isinstance(jobs_data, dict):
            raise ValueError(
                f"{self.path}: 'jobs' must be a mapping, "
                f"got {type(jobs_data).__name__}"
            )
        jobs: dict[str, Job] = {
            job_name: self._parse_job(job_name, job_data)
            for job_name, job_data in jobs_data.items()
        }
        return Workflow(name=name, on=on, env=env, jobs=jobs, raw=data)

    def _parse_on(self, data: dict[Any, Any]) -> dict[str, Any]:
        """Normaliza `on:` para mapping.

        PyYAML segue o resolver booleano do YAML 1.1, onde a chave crua `on`
        vira a chave booleana `True` — por isso `data.get("on")` erra.
        """
        raw = data.get("on", data.get(True, data.get("true")))
        if raw is None:
            return {}
        if isinstance(raw, str):
            return {raw: {}}
        if isinstance(raw, list):
            return {event: {} for event in raw}
        if not isinstance(raw, dict):
            raise ValueError(
                f"{self.path}: 'on' must be a string, list or mapping, "
                f"got {type(raw).__name__}"
            )
        return raw

    def _parse_job(self, name: str, data: dict[str, Any]) -> Job:
        if not isinstance(data, dict):
            raise ValueError(
                f"{self.path}: job '{name}' must be a mapping, "
                f"got {type(data).__name__}"
            )
        needs = data.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        steps_data = data.get("steps", [])
        if not isinstance(steps_data, list):
            raise ValueError(
                f"{self.path}: job '{name}': 'steps' must be a list, "
                f"got {type(steps_data).__name__}"
            )
        steps = [self._parse_step(s, i, name) for i, s in enumerate(steps_data)]
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

    def _parse_step(self, data: dict[str, Any], index: int, job: str) -> Step:
        if not isinstance(data, dict):
            raise ValueError(
                f"{self.path}: job '{job}': step {index} must be a mapping, "
                f"got {type(data).__name__}"
            )
        return Step(
            name=data.get("name", ""),
            run=data.get("run", ""),
            uses=data.get("uses", ""),
            with_args=data.get("with", {}),
            if_condition=data.get("if", ""),
            env=data.get("env", {}),
        )
