PYTHON ?= .venv/bin/python

.PHONY: setup doctor status progress wait validate validate-rag final-validate benchmark test check run index download docker-up launchd-install launchd-uninstall launchd-status

setup:
	scripts/setup_macos.sh

doctor:
	scripts/doctor.sh

status:
	scripts/status.sh

progress:
	scripts/progress.sh

wait:
	scripts/wait_for_index.sh

validate:
	scripts/validate_rag.sh

validate-rag:
	scripts/validate_rag.sh --rag

final-validate:
	scripts/validate_rag.sh --require-full-index --rag

benchmark:
	scripts/benchmark.sh

test:
	$(PYTHON) -m unittest discover -s tests

check:
	scripts/check_all.sh

run:
	scripts/run_native.sh

index:
	scripts/index_full_native.sh

download:
	$(PYTHON) ingest.py --all --download-only

docker-up:
	docker compose up --build

launchd-install:
	scripts/launchd_manage.sh install

launchd-uninstall:
	scripts/launchd_manage.sh uninstall

launchd-status:
	scripts/launchd_manage.sh status
