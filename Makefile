PYTHON ?= .venv/bin/python

.PHONY: setup doctor status progress validate validate-rag benchmark test run index download docker-up

setup:
	scripts/setup_macos.sh

doctor:
	scripts/doctor.sh

status:
	scripts/status.sh

progress:
	scripts/progress.sh

validate:
	scripts/validate_rag.sh

validate-rag:
	scripts/validate_rag.sh --rag

benchmark:
	scripts/benchmark.sh

test:
	$(PYTHON) -m unittest discover -s tests

run:
	scripts/run_native.sh

index:
	scripts/index_full_native.sh

download:
	$(PYTHON) ingest.py --all --download-only

docker-up:
	docker compose up --build
