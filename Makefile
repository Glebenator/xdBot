.PHONY: install install-dev run lint test compile check

install:
	python -m pip install -r requirements.txt

install-dev: install
	python -m pip install -r requirements-dev.txt

run:
	python main.py

lint:
	python -m ruff check .

test:
	python -m pytest

compile:
	python -m compileall -q main.py config.py cogs utils tests

check: compile lint test
	python main.py --check
