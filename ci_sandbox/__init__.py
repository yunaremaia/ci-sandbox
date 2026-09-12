"""CI Sandbox — Simulador local de pipelines CI.

Simula a execução de workflows do GitHub Actions sem executar nada.
Resolve DAG, avalia condições `if`, e mostra quais jobs rodam vs. skipam.
"""

from ci_sandbox.models import Job, Step, Workflow
from ci_sandbox.parser import WorkflowParser
from ci_sandbox.simulator import CISimulator

__version__ = "0.1.0"

__all__ = ["__version__", "CISimulator", "Workflow", "WorkflowParser", "Job", "Step"]
