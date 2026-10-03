# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-03

First tagged release. `0.1.0` is the version already declared in `pyproject.toml`;
nothing was ever tagged or published before this date, so everything below ships
together as the initial release.

### Not on PyPI

**`ci-sandbox` is not on PyPI and `pip install ci-sandbox` does not work.**
Install from git:

```bash
pip install git+https://github.com/yunaremaia/ci-sandbox.git
```

This repository has no publish workflow and no PyPI project, so no upload has ever
been attempted. The bare `ci-sandbox` name on PyPI was checked and is unclaimed,
but registering a trusted publisher for this repository has not been done, so
nothing is published there today.

### Added

- Local CI pipeline simulator: parses `.github/workflows/*.yml` files and reports
  which jobs would run and which would be skipped, without executing anything.
- Job DAG resolution through `needs`, evaluated in topological order so a skipped
  job correctly causes its dependents to be skipped.
- `if:` condition evaluation against the simulated event context (`github.event_name`,
  `github.ref`, `github.head_ref`, branch name), with the reason for each skip
  reported to the user rather than silently dropping the job.
- Two CLI commands:
  - `ci-sandbox simulate <workflow>` — simulate one workflow; supports
    `--event`, `--branch`, `--steps`, and `-s KEY=VALUE` for secrets.
  - `ci-sandbox list-workflows` — list the workflows found in a directory with
    their job counts.
- Colored terminal output distinguishing run from skipped, with a per-run summary.
- Python API: `WorkflowParser`, `CISimulator`, and the `Workflow` / `Job` / `Step`
  models.
- GitHub Actions CI workflow.
- `CONTRIBUTING.md`, `SECURITY.md`, `FUNDING.yml`, an MIT `LICENSE`, and PR,
  bug-report and feature-request templates.
- README with a quickstart, a worked example for both a `push` and a
  `pull_request` event, and a documented limitations section.

### Fixed

- CI failing on every run: the workflow installed no dependencies and had no
  `setup-python` step, so `import ci_sandbox` could not resolve. Both are now set
  up before the tests run.
- `__pycache__` bytecode was tracked in git; it is now untracked and build
  artifacts are ignored.

### Known limitations

These are real gaps in this release, not bugs to be discovered later:

- Steps are never executed; only the skip/run logic is simulated.
- GitHub Actions expression support is partial — only the contexts listed above
  are resolved.
- `matrix` support is basic.

[0.1.0]: https://github.com/yunaremaia/ci-sandbox/releases/tag/v0.1.0