"""Testes do CI Sandbox."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ci_sandbox.models import Job, Step, Workflow
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
