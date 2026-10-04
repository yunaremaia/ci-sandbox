"""Testes do CI Sandbox."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ci_sandbox.models import Job, Workflow
from ci_sandbox.parser import WorkflowParser
from ci_sandbox.simulator import CISimulator


@pytest.fixture
def sample_workflow(tmp_path: Path) -> Path:
    """Cria um workflow YAML de exemplo."""
    data = {
        "name": "CI",
        "on": ["push", "pull_request"],
        "env": {"NODE_ENV": "test"},
        "jobs": {
            "lint": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "ruff check ."},
                ],
            },
            "test": {
                "needs": "lint",
                "runs-on": "ubuntu-latest",
                "if": "github.event_name == 'push'",
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "pytest"},
                ],
            },
            "deploy": {
                "needs": "test",
                "runs-on": "ubuntu-latest",
                "if": "github.ref == 'refs/heads/main'",
                "steps": [
                    {"run": "echo Deploying..."},
                ],
            },
        },
    }
    path = tmp_path / "ci.yml"
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


@pytest.fixture
def parser() -> WorkflowParser:
    return WorkflowParser(Path("dummy.yml"))


class TestWorkflowParser:
    def test_parse_basic(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        assert wf.name == "CI"
        assert "push" in wf.on
        assert "pull_request" in wf.on
        assert len(wf.jobs) == 3

    def test_parse_jobs(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        assert "lint" in wf.jobs
        assert "test" in wf.jobs
        assert "deploy" in wf.jobs

    def test_parse_job_details(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        lint = wf.jobs["lint"]
        assert lint.runs_on == "ubuntu-latest"
        assert len(lint.steps) == 2
        assert lint.steps[0].uses == "actions/checkout@v4"
        assert lint.steps[1].run == "ruff check ."

    def test_parse_needs(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        assert wf.jobs["test"].needs == ["lint"]
        assert wf.jobs["deploy"].needs == ["test"]

    def test_parse_if_condition(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        assert wf.jobs["test"].if_condition == "github.event_name == 'push'"
        assert wf.jobs["deploy"].if_condition == "github.ref == 'refs/heads/main'"

    def test_parse_env(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        assert wf.env["NODE_ENV"] == "test"


class TestCISimulator:
    def test_basic_run(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        sim = CISimulator(wf, event="push", branch="main")
        jobs = sim.run()
        assert jobs["lint"].status == "success"
        assert jobs["test"].status == "success"
        assert jobs["deploy"].status == "success"

    def test_pull_request_skips_test(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        sim = CISimulator(wf, event="pull_request", branch="feature-x")
        jobs = sim.run()
        assert jobs["lint"].status == "success"
        assert jobs["test"].status == "skipped"
        assert "github.event_name" in jobs["test"].skipped_because

    def test_deploy_skipped_on_feature_branch(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        sim = CISimulator(wf, event="push", branch="feature-x")
        jobs = sim.run()
        assert jobs["lint"].status == "success"
        assert jobs["test"].status == "success"
        assert jobs["deploy"].status == "skipped"
        assert "github.ref" in jobs["deploy"].skipped_because

    def test_cascade_skip(self, sample_workflow: Path):
        """Se test é skipado, deploy também deve ser."""
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        sim = CISimulator(wf, event="pull_request", branch="main")
        jobs = sim.run()
        assert jobs["lint"].status == "success"
        assert jobs["test"].status == "skipped"
        assert jobs["deploy"].status == "skipped"
        assert "dependency" in jobs["deploy"].skipped_because

    def test_event_not_triggered(self, tmp_path: Path):
        data = {
            "name": "Deploy",
            "on": ["workflow_dispatch"],
            "jobs": {
                "deploy": {
                    "runs-on": "ubuntu-latest",
                    "steps": [{"run": "echo hi"}],
                }
            },
        }
        path = tmp_path / "deploy.yml"
        with open(path, "w") as f:
            yaml.dump(data, f)
        parser = WorkflowParser(path)
        wf = parser.parse()
        sim = CISimulator(wf, event="push", branch="main")
        jobs = sim.run()
        assert jobs["deploy"].status == "skipped"
        assert "event" in jobs["deploy"].skipped_because

    def test_execution_order(self, sample_workflow: Path):
        parser = WorkflowParser(sample_workflow)
        wf = parser.parse()
        sim = CISimulator(wf, event="push", branch="main")
        sim.run()
        assert sim.execution_order == [["lint"], ["test"], ["deploy"]]


class TestExpressionEvaluation:
    def test_contains(self):
        wf = Workflow(name="test")
        sim = CISimulator(wf)
        assert sim._eval_expression("contains('hello world', 'hello')") is True
        assert sim._eval_expression("contains('hello world', 'xyz')") is False

    def test_starts_with(self):
        wf = Workflow(name="test")
        sim = CISimulator(wf)
        assert sim._eval_expression("startsWith('hello world', 'hello')") is True
        assert sim._eval_expression("startsWith('hello world', 'world')") is False

    def test_equality(self):
        wf = Workflow(name="test")
        sim = CISimulator(wf, branch="main")
        assert sim._eval_expression("github.ref_name == 'main'") is True
        assert sim._eval_expression("github.ref_name == 'dev'") is False

    def test_secrets_check(self):
        wf = Workflow(name="test")
        sim = CISimulator(wf, secrets={"API_KEY": "123"})
        assert sim._eval_expression("secrets.API_KEY") is True
        assert sim._eval_expression("secrets.MISSING") is False

    def test_dollar_curly(self):
        wf = Workflow(name="test")
        sim = CISimulator(wf)
        assert sim._eval_expression("${{ true }}") is True
        assert sim._eval_expression("${{ contains('abc', 'a') }}") is True

    def test_failure_reflects_failed_job(self):
        """#76: failure() is true when a job in the run has status failure."""
        wf = Workflow(
            name="test",
            jobs={
                "a": Job(name="a", status="success"),
                "b": Job(name="b", status="failure"),
            },
        )
        assert CISimulator(wf)._eval_expression("failure()") is True

    def test_failure_false_without_failures(self):
        wf = Workflow(name="test", jobs={"a": Job(name="a", status="success")})
        assert CISimulator(wf)._eval_expression("failure()") is False

    def test_success_false_when_a_job_skipped(self):
        wf = Workflow(name="test", jobs={"a": Job(name="a", status="skipped")})
        assert CISimulator(wf)._eval_expression("success()") is False

    def test_success_true_when_every_evaluated_job_succeeded(self):
        wf = Workflow(
            name="test",
            jobs={
                "a": Job(name="a", status="success"),
                "b": Job(name="b", status="pending"),
            },
        )
        assert CISimulator(wf)._eval_expression("success()") is True

    def test_cancelled_is_false(self):
        """No cancellation source exists yet, so the answer is always False."""
        assert CISimulator(Workflow(name="test"))._eval_expression("cancelled()") is False


def _raw(tmp_path: Path, filename: str, text: str) -> Path:
    """Writes a workflow verbatim, so YAML key quirks survive (bare `on:`)."""
    path = tmp_path / filename
    path.write_text(text)
    return path


class TestOnTriggers:
    """#83: PyYAML applies the YAML 1.1 bool resolver, so `on` arrives as True."""

    PUSH_ONLY = (
        "name: Deploy\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo build\n"
    )

    def test_on_mapping_is_parsed(self, tmp_path: Path):
        wf = WorkflowParser(_raw(tmp_path, "map.yml", self.PUSH_ONLY)).parse()
        assert "push" in wf.on

    def test_on_string_is_parsed(self, tmp_path: Path):
        wf = WorkflowParser(_raw(tmp_path, "str.yml", "on: push\njobs: {}\n")).parse()
        assert wf.on == {"push": {}}

    def test_on_list_is_parsed(self, tmp_path: Path):
        wf = WorkflowParser(
            _raw(tmp_path, "list.yml", "on: [push, release]\njobs: {}\n")
        ).parse()
        assert set(wf.on) == {"push", "release"}

    def test_undeclared_event_skips_everything(self, tmp_path: Path):
        sim = CISimulator(
            WorkflowParser(_raw(tmp_path, "deploy.yml", self.PUSH_ONLY)).parse(),
            event="release",
            branch="main",
        )
        jobs = sim.run()
        assert jobs["build"].status == "skipped"
        assert "release" in jobs["build"].skipped_because
        # o renderizador percorre execution_order: sem isto, nada aparece
        assert sim.execution_order == [["build"]]

    def test_declared_event_runs(self, tmp_path: Path):
        sim = CISimulator(
            WorkflowParser(_raw(tmp_path, "deploy.yml", self.PUSH_ONLY)).parse(),
            event="push",
            branch="main",
        )
        assert sim.run()["build"].status == "success"


class TestCycleDetection:
    """#77: a dependency cycle is an error, not a silently dropped job."""

    @staticmethod
    def _wf(needs: dict[str, str]) -> Workflow:
        return Workflow(
            name="C",
            jobs={
                name: Job(name=name, needs=[need] if need else [])
                for name, need in needs.items()
            },
        )

    def test_simple_cycle_raises_with_path(self):
        sim = CISimulator(self._wf({"a": "b", "b": "a"}))
        with pytest.raises(ValueError) as exc:
            sim.run()
        assert "a → b → a" in str(exc.value)

    def test_complex_cycle_names_every_job(self):
        sim = CISimulator(self._wf({"a": "b", "b": "c", "c": "a"}))
        with pytest.raises(ValueError) as exc:
            sim.run()
        message = str(exc.value)
        assert "Circular dependency detected" in message
        assert all(name in message for name in ("a", "b", "c"))

    def test_acyclic_workflow_still_runs(self):
        sim = CISimulator(self._wf({"a": "", "b": "a"}))
        jobs = sim.run()
        assert sim.execution_order == [["a"], ["b"]]
        assert jobs["b"].status == "success"


class TestMalformedWorkflows:
    """#75: malformed documents get a friendly ValueError, not an AttributeError."""

    def test_jobs_as_string(self, tmp_path: Path):
        path = _raw(tmp_path, "bad.yml", 'on: push\njobs: "invalid"\n')
        with pytest.raises(ValueError, match="'jobs' must be a mapping"):
            WorkflowParser(path).parse()

    def test_steps_as_string(self, tmp_path: Path):
        path = _raw(tmp_path, "bad.yml", "jobs:\n  build:\n    steps: nope\n")
        with pytest.raises(ValueError, match="'steps' must be a list"):
            WorkflowParser(path).parse()

    def test_step_as_string(self, tmp_path: Path):
        path = _raw(tmp_path, "bad.yml", "jobs:\n  build:\n    steps:\n      - echo hi\n")
        with pytest.raises(ValueError, match="step .* must be a mapping"):
            WorkflowParser(path).parse()

    def test_on_as_integer(self, tmp_path: Path):
        path = _raw(tmp_path, "bad.yml", "on: 42\njobs: {}\n")
        with pytest.raises(ValueError, match="'on' must be a string, list or mapping"):
            WorkflowParser(path).parse()

    def test_root_not_a_mapping(self, tmp_path: Path):
        path = _raw(tmp_path, "bad.yml", "- just\n- a list\n")
        with pytest.raises(ValueError, match="root must be a mapping"):
            WorkflowParser(path).parse()

    def test_error_names_the_file(self, tmp_path: Path):
        path = _raw(tmp_path, "broken.yml", 'jobs: "invalid"\n')
        with pytest.raises(ValueError, match="broken.yml"):
            WorkflowParser(path).parse()

    def test_valid_workflow_still_parses(self, sample_workflow: Path):
        wf = WorkflowParser(sample_workflow).parse()
        assert len(wf.jobs) == 3
