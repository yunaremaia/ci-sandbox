# CI Sandbox

Simulador local de pipelines CI. Veja quais jobs rodam e quais são skipados — sem executar nada.

## O que faz

- Faz parse de workflows do GitHub Actions (`.github/workflows/*.yml`)
- Resolve o DAG de jobs (dependências `needs`)
- Avalia condições `if` para determinar skip/run
- Expande estratégias de `matrix` mostrando combinações individuais com suas variáveis
- Mostra resultado colorido no terminal

## Instalação

```bash
pip install ci-sandbox
```

## Uso

```bash
# Simular um workflow
ci-sandbox simulate .github/workflows/ci.yml

# Simular evento específico
ci-sandbox simulate .github/workflows/ci.yml --event pull_request --branch feature-x

# Com secrets
ci-sandbox simulate .github/workflows/ci.yml -s DATABASE_URL=postgres://localhost

# Mostrar steps
ci-sandbox simulate .github/workflows/ci.yml --steps

# Listar workflows do repo
ci-sandbox list-workflows
```

## Exemplo

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ruff check .

  test:
    needs: lint
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - run: pytest

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying..."
```

```bash
$ ci-sandbox simulate .github/workflows/ci.yml --event push --branch main
🔧 CI
   Event: push | Branch: main | Ref: refs/heads/main

  ✓ lint [ubuntu-latest]
  ↓
  ✓ test [ubuntu-latest]
  ↓
  ✓ deploy [ubuntu-latest]

  ══ 3 success · 0 skipped (3 jobs) ══
```

```bash
$ ci-sandbox simulate .github/workflows/ci.yml --event pull_request --branch feature-x
🔧 CI
   Event: pull_request | Branch: feature-x | Ref: refs/heads/feature-x

  ✓ lint [ubuntu-latest]
  ↓
  ○ test (condition: github.event_name == 'push')
  ↓
  ○ deploy (dependency 'test' did not succeed)

  ══ 1 success · 2 skipped (3 jobs) ══
```

### Exemplo com Matrix Strategy

Workflows com `strategy.matrix` têm seus jobs expandidos em entradas individuais exibindo suas variáveis e `runs-on` resolvidos:

```yaml
jobs:
  test:
    strategy:
      matrix:
        node: [18, 20]
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
```

```bash
$ ci-sandbox simulate .github/workflows/ci.yml
🔧 CI
   Event: push | Branch: main | Ref: refs/heads/main

  ✓ test (node=18, os=macos-latest) [macos-latest]
  ✓ test (node=18, os=ubuntu-latest) [ubuntu-latest]
  ✓ test (node=20, os=macos-latest) [macos-latest]
  ✓ test (node=20, os=ubuntu-latest) [ubuntu-latest]

  ══ 4 success · 0 skipped (4 jobs) ══
```

## Limitações

- Não executa steps (só simula a lógica de skip/run)
- Não suporta todos os functions do GitHub Actions (implementação parcial)

## Licença

MIT
