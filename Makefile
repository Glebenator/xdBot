.PHONY: install install-dev run lint test compile check

install:
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-dev.txt

run:
	python main.py

lint:
	python -m ruff check .

test:
	python -m pytest -q

compile:
	python -m compileall .

check: compile lint test
