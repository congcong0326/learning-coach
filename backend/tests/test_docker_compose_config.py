from pathlib import Path


def test_frontend_dev_service_installs_dependencies_non_interactively() -> None:
    compose = Path("infra/compose/docker-compose.dev.yml").read_text(encoding="utf-8")

    assert "CI=true pnpm install --frozen-lockfile" in compose
    assert "pnpm dev --host 0.0.0.0" in compose
