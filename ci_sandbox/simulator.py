"""Simulador de pipelines CI."""

from __future__ import annotations

import re
from typing import Any

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
        self.jobs: dict[str, Job] = self._expand_jobs(self.workflow.jobs)

    def _expand_jobs(self, raw_jobs: dict[str, Job]) -> dict[str, Job]:
        expanded: dict[str, Job] = {}
        mapping: dict[str, list[str]] = {}

        for job_name, job in raw_jobs.items():
            matrix = job.strategy.get("matrix") if job.strategy else None
            if not matrix or not isinstance(matrix, dict):
                mapping[job_name] = [job_name]
                expanded[job_name] = job
                continue

            combinations = self._build_matrix_combinations(matrix)
            if not combinations:
                mapping[job_name] = [job_name]
                expanded[job_name] = job
                continue

            sub_names: list[str] = []
            for combo in combinations:
                vars_str = ", ".join(f"{k}={combo[k]}" for k in sorted(combo.keys()))
                sub_name = f"{job_name} ({vars_str})"
                sub_names.append(sub_name)

                runs_on = job.runs_on
                for k, v in combo.items():
                    runs_on = runs_on.replace(f"${{{{ matrix.{k} }}}}", str(v))
                    runs_on = runs_on.replace(f"${{{{matrix.{k}}}}}", str(v))
                    runs_on = runs_on.replace(f"matrix.{k}", str(v))

                if_cond = job.if_condition
                for k, v in combo.items():
                    if_cond = if_cond.replace(f"${{{{ matrix.{k} }}}}", str(v))
                    if_cond = if_cond.replace(f"${{{{matrix.{k}}}}}", str(v))
                    if_cond = if_cond.replace(f"matrix.{k}", str(v))

                sub_job = Job(
                    name=sub_name,
                    runs_on=runs_on,
                    needs=list(job.needs),
                    if_condition=if_cond,
                    steps=job.steps,
                    env=dict(job.env),
                    services=dict(job.services),
                    strategy=dict(job.strategy),
                    outputs=dict(job.outputs),
                    matrix_vars=combo,
                    status=job.status,
                    skipped_because=job.skipped_because,
                )
                expanded[sub_name] = sub_job
            mapping[job_name] = sub_names

        for job in expanded.values():
            new_needs: list[str] = []
            for n in job.needs:
                if n in mapping:
                    new_needs.extend(mapping[n])
                else:
                    new_needs.append(n)
            job.needs = new_needs

        return expanded

    def _build_matrix_combinations(self, matrix: dict[str, Any]) -> list[dict[str, Any]]:
        import itertools

        keys = [k for k in matrix.keys() if k not in ("include", "exclude")]
        if not keys and "include" not in matrix:
            return []

        if keys:
            dimensions = [
                matrix[k] if isinstance(matrix[k], list) else [matrix[k]]
                for k in keys
            ]
            combos = [dict(zip(keys, prod)) for prod in itertools.product(*dimensions)]
        else:
            combos = []

        for inc in matrix.get("include", []):
            if isinstance(inc, dict):
                matched = False
                for c in combos:
                    if all(c.get(k) == inc[k] for k in keys if k in inc):
                        c.update(inc)
                        matched = True
                if not matched:
                    combos.append(dict(inc))

        excludes = matrix.get("exclude", [])
        if excludes:
            filtered = []
            for c in combos:
                excluded = False
                for exc in excludes:
                    if isinstance(exc, dict) and all(c.get(k) == exc[k] for k in exc):
                        excluded = True
                        break
                if not excluded:
                    filtered.append(c)
            combos = filtered

        return combos

    def run(self) -> dict[str, Job]:
        """Executa simulação e retorna jobs com status."""
        jobs = self.jobs
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
        jobs = self.jobs
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
            need_job = self.jobs.get(need)
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
