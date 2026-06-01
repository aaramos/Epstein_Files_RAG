PYTHON ?= .venv/bin/python

.PHONY: setup doctor status progress watch wait wait-notify validate validate-rag final-validate final-audit partial-audit partial-audit-json smoke-app diagnostics benchmark test check run index download build-faiss chroma-rebuild chroma-vector docker-up launchd-install launchd-uninstall launchd-status launchd-validate

setup:
	scripts/setup_macos.sh

doctor:
	scripts/doctor.sh

status:
	scripts/status.sh

progress:
	scripts/progress.sh

watch:
	scripts/progress.sh --watch $${INTERVAL_SECONDS:-60}

wait:
	scripts/wait_for_index.sh

wait-notify:
	MACOS_NOTIFY_ON_COMPLETE=1 scripts/wait_for_index.sh

validate:
	scripts/validate_rag.sh

validate-rag:
	scripts/validate_rag.sh --rag

final-validate:
	scripts/validate_rag.sh --require-full-index --rag

final-audit:
	scripts/final_audit.sh

partial-audit:
	scripts/final_audit.sh --allow-incomplete --skip-app

partial-audit-json:
	scripts/final_audit.sh --allow-incomplete --skip-app --json

smoke-app:
	scripts/smoke_app.sh

diagnostics:
	scripts/collect_diagnostics.sh

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

build-faiss:
	$(PYTHON) scripts/build_faiss.py

chroma-rebuild:
	scripts/rebuild_chroma_native.sh

chroma-vector:
	$(PYTHON) scripts/chroma_vector_diagnostics.py

docker-up:
	docker compose up --build

launchd-install:
	scripts/launchd_manage.sh install

launchd-uninstall:
	scripts/launchd_manage.sh uninstall

launchd-status:
	scripts/launchd_manage.sh status

launchd-validate:
	scripts/launchd_manage.sh validate
