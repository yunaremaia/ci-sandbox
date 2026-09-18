"""Simulador de pipelines CI."""

from __future__ import annotations

import re

from ci_sandbox.models import Job, Workflow


class CISimulator:
    """Simula execução do pipeline com base no contexto fornecido."""

    def __init__(
        self,
        workflow: Workflow,
        event: str = "push",
        branch: str = "main",
        ref: str | None = None,
        secrets: dict[str, str] | None = None,
        inputs: dict[str, str] | None = None,
    ):
        self.workflow = workflow
        self.event = event
        self.branch = branch
        self.ref = ref or f"refs/heads/{branch}"
        self.secrets = secrets or {}
        self.inputs = inputs or {}
        self.execution_order: list[list[str]] = []

    def run(self) -> dict[str, Job]:
        """Executa simulação e retorna jobs com status."""
        jobs = self.workflow.jobs
        if not self._event_triggers():
            for job in jobs.values():
                job.status = "skipped"
                job.skipped_because = f"event '{self.event}' does not trigger"
            return jobs

        sorted_groups = self._topological_sort()

        for group in sorted_groups:
            for job_name in group:
                job = jobs[job_name]
                status = self._evaluate_job(job)
                job.status = status
            self.execution_order.append(sorted(group))

        return jobs

    def _event_triggers(self) -> bool:
        on = self.workflow.on
        if not on:
            return True
        return self.event in on

    def _topological_sort(self) -> list[list[str]]:
        jobs = self.workflow.jobs
        in_degree: dict[str, int] = {n: 0 for n in jobs}
        dependents: dict[str, list[str]] = {n: [] for n in jobs}

        for job_name, job in jobs.items():
            for need in job.needs:
                if need in jobs:
                    in_degree[job_name] += 1
                    dependents[need].append(job_name)

        ready = sorted([n for n, d in in_degree.items() if d == 0])
        groups: list[list[str]] = []

        while ready:
            groups.append(ready)
            next_ready: list[str] = []
            for node in ready:
                for dep in dependents[node]:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        next_ready.append(dep)
            ready = sorted(next_ready)

        return groups

    def _evaluate_job(self, job: Job) -> str:
        for need in job.needs:
            need_job = self.workflow.jobs.get(need)
            if need_job and need_job.status in ("failure", "skipped"):
                job.skipped_because = f"dependency '{need}' did not succeed"
                return "skipped"

        if job.if_condition:
            result = self._eval_expression(job.if_condition)
            if not result:
                job.skipped_because = f"condition: {job.if_condition}"
                return "skipped"

        return "success"

    def _eval_expression(self, expr: str) -> bool:
        if not expr:
            return True
        expr = expr.strip()

        if expr.startswith("${{") and expr.endswith("}}"):
            expr = expr[3:-2].strip()

        if expr == "always()":
            return True
        if expr == "failure()":
            return False
        if expr == "cancelled()":
            return False
        if expr == "success()":
            return True

        m = re.match(r"contains\((.+),\s*(.+)\)", expr)
        if m:
            search = self._resolve_value(m.group(1).strip())
            item = self._resolve_value(m.group(2).strip())
            return item in str(search)

        m = re.match(r"startsWith\((.+),\s*(.+)\)", expr)
        if m:
            search = self._resolve_value(m.group(1).strip())
            item = self._resolve_value(m.group(2).strip())
            return str(search).startswith(str(item))

        m = re.match(r"endsWith\((.+),\s*(.+)\)", expr)
        if m:
            search = self._resolve_value(m.group(1).strip())
            item = self._resolve_value(m.group(2).strip())
            return str(search).endswith(str(item))

        if "==" in expr:
            parts = expr.split("==", 1)
            left = self._resolve_value(parts[0].strip())
            right = self._resolve_value(parts[1].strip())
            return str(left) == str(right)

        if "!=" in expr:
            parts = expr.split("!=", 1)
            left = self._resolve_value(parts[0].strip())
            right = self._resolve_value(parts[1].strip())
            return str(left) != str(right)

        if expr == "true":
            return True
        if expr == "false":
            return False

        if "github.event_name" in expr:
            m = re.search(r"github\.event_name\s*==\s*'([^']+)'", expr)
            if m:
                return self.event == m.group(1)

        if "github.ref" in expr:
            m = re.search(r"github\.ref\s*==\s*'([^']+)'", expr)
            if m:
                return self.ref == m.group(1)

        m = re.match(r"secrets\.(\w+)", expr)
        if m:
            return m.group(1) in self.secrets

        return True

    def _resolve_value(self, value: str) -> str:
        value = value.strip().strip("'\"")
        if value == "github.ref":
            return self.ref
        if value == "github.event_name":
            return self.event
        if value == "github.ref_name":
            return self.branch
        if value.startswith("env.") and len(value) > 4:
            return self.workflow.env.get(value[4:], "")
        if value.startswith("secrets.") and len(value) > 8:
            return self.secrets.get(value[8:], "")
        return value
