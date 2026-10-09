.PHONY: install test test-integration lint format typecheck check

install:
	pip install -e .[dev]

test:
	# Tests unitarios y de contrato (contra el fake); los marcados
	# 'integration' se saltan salvo que haya Moodle real configurado.
	pytest

test-integration:
	# Tests de contrato contra Moodle real: requiere MOODLE_URL y
	# MOODLE_TOKEN de un moodle-docker con el plugin local_courseascode.
	pytest -m integration

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .

typecheck:
	mypy

check: lint typecheck test
