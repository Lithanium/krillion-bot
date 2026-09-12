.PHONY: venv test lint run deploy

venv:
	python3 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

run:
	.venv/bin/python -m krillion_bot

# make deploy HOST=ubuntu@1.2.3.4 [KEY=~/.ssh/oracle.key]
deploy:
	./deploy/deploy.sh $(HOST) $(KEY)
