UV ?= $(if $(wildcard .venv/bin/uv),.venv/bin/uv,uv)
UV_CACHE_DIR ?= .uv-cache

.PHONY: check format-check lint typecheck unit postgres-integration opa-contract isolation-contract benchmark-journal benchmark-journal-stream aws-contract aws-infra

check: format-check lint typecheck unit

format-check:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen ruff format --check .

lint:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen ruff check .

typecheck:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen mypy

unit:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen pytest -m "not aws_optional and not postgres_integration and not opa_integration"

postgres-integration:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen pytest -m postgres_integration

opa-contract:
	SENTINEL_TEST_OPA_DOCKER=1 UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen pytest -m opa_integration

isolation-contract:
	SENTINEL_TEST_DOCKER_ISOLATION=1 UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen pytest -q tests/test_isolation.py::test_real_docker_container_cannot_read_unmounted_controller_or_use_network

benchmark-journal:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen python benchmarks/journal_scale.py --events 3000
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen python benchmarks/journal_scale.py --events 10000
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen python benchmarks/journal_scale.py --events 50000

benchmark-journal-stream:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen python benchmarks/journal_scale.py --events 3000 --mode stream
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen python benchmarks/journal_scale.py --events 10000 --mode stream
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen python benchmarks/journal_scale.py --events 50000 --mode stream

aws-contract:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen --extra aws pytest tests/test_aws_sdk_contract.py tests/test_cloud_evidence.py tests/test_aws_infra.py

aws-infra:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen --group aws-dev cfn-lint deploy/aws/evidence-stack.json
