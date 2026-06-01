# <img src="logo.png" width="50" align="center"> Epstein Files RAG Explorer 🔍

An open-source Retrieval-Augmented Generation (RAG) platform to explore and analyze the unsealed Jeffrey Epstein court documents. Built with LangChain, ChromaDB, and Streamlit.

![Screenshot](pic.png)

## 🚀 Features
- **Open Stack**: Fully open-source tools and models.
- **Local & Fast**: Support for local execution via Ollama or high-speed cloud inference via Groq/OpenRouter.
- **Automated Ingestion**: Easily download and index curated parquet data from Hugging Face.
- **Strict Guardrails**: Designed to stay strictly within the context of the investigative documents.

---

## 🛠️ Setup Instructions

### Mac Studio / oMLX Quick Start
This fork is tuned for Apple Silicon and local oMLX:

```bash
scripts/setup_macos.sh
make doctor
make download
make index
make run
```

For the full dataset:

```bash
make download
make index
```

Or use the native helper:

```bash
EMBEDDING_DEVICE=auto scripts/index_full_native.sh
```

If you already have the full dataset elsewhere, link it during setup:

```bash
SOURCE_DATA_DIR=/path/to/data scripts/setup_macos.sh
```

The ingester is resumable. It records completed parquet files in
`chroma_db/ingest_manifest.json`, streams parquet row batches to keep memory
bounded, and uses stable chunk IDs.

To check progress without importing the ML stack:

```bash
.venv/bin/python ingest.py --status --check-hub
# or
scripts/status.sh
scripts/progress.sh
# Poll until indexing is complete, then run final validation:
make wait
```

`scripts/progress.sh` also reports manifest and index-log freshness. If an
active indexer has not written to `runtime/index_full.log` for more than
`INDEX_STALE_SECONDS` seconds, it prints a warning. Use
`scripts/progress.sh --json` for machine-readable monitor output.

To run a Mac readiness check:

```bash
scripts/doctor.sh
scripts/validate_rag.sh
# Include a short oMLX generation call:
scripts/validate_rag.sh --rag
scripts/benchmark.sh
```

The same commands are exposed as Make targets: `make status`, `make progress`,
`make wait`, `make validate`, `make validate-rag`, `make final-validate`,
`make benchmark`, `make test`, and `make check`.

This fork also includes `constraints-macos-arm64.txt`, a known-good constraints
set captured from the working Mac Studio environment. `scripts/setup_macos.sh`
uses it automatically when present.

The Streamlit config uses polling file watching on macOS to avoid FSEvents
startup failures seen in headless/local-service runs.

`make check` intentionally skips extra retrieval/benchmark passes while the full
indexer is actively writing to Chroma. Use `CHECK_DURING_INDEX=1 make check`
only when you explicitly want to stress concurrent read/write behavior.

Useful ingestion tuning knobs:

- `--row-batch-size`: parquet rows to stream at once.
- `--batch-size`: chunks to embed/write to Chroma at once.
- `--embedding-device mps`: request Apple Silicon acceleration for native runs.
  If PyTorch cannot initialize MPS on the current macOS/runtime, the app falls
  back to CPU automatically.

Useful local generation knobs:

- `OMLX_MAX_TOKENS`: response cap for local oMLX calls.
- `OMLX_TIMEOUT_SECONDS`: request timeout for local oMLX calls.
- `LLM_TEMPERATURE`: shared temperature setting for all providers.
- `APP_ALLOW_QUERY_DURING_INDEX`: defaults to `0` so the Streamlit app pauses
  questions while Chroma is actively being written. Set it to `1` only if you
  want to query the partial index during ingestion.

After the full corpus finishes indexing, run `make final-validate`. It fails
until all expected parquet files are indexed, then performs retrieval plus a
short oMLX generation check.

For unattended completion, run `make wait`. It prints progress on an interval
and automatically runs final validation when the manifest shows all files are
indexed. Set `RUN_FINAL_VALIDATE=0 make wait` to only wait and report completion.

### Docker
The app can run in Docker Compose and connect back to host oMLX:

```bash
docker compose up --build
```

The compose file mounts `./data`, `./chroma_db`, and your host
`~/.omlx/settings.json` as a read-only secret. Containers do not get Apple MPS
acceleration, so native Mac execution is preferred for high-throughput
embedding/indexing.

The Docker image intentionally does not use `constraints-macos-arm64.txt` by
default because that file captures the native Mac Studio environment, not the
Linux container runtime. To force a constraint file for a custom build, pass
`--build-arg PIP_CONSTRAINT_FILE=<file>`.

### macOS LaunchAgent Templates
Example LaunchAgent plists live in `launchd/`:

- `com.epstein-rag.app.plist.example` starts the Streamlit app.
- `com.epstein-rag.indexer.plist.example` runs the full native indexer.

Copy a template into `~/Library/LaunchAgents/`, remove the `.example` suffix,
then load it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<file>.plist`.
The templates use this checkout path:
`/Users/macstudio/Documents/RAG/Epstein_Files_RAG_macstudio`.

You can also install the app and indexer LaunchAgents from the current checkout:

```bash
make launchd-install
make launchd-status
```

Use `scripts/launchd_manage.sh install app` or `install indexer` to install
only one service. The helper renders the plist files with the current checkout
path and writes logs under `runtime/`.

### General Prerequisites
- **Python 3.10+** (Recommend using a virtual environment).
- **Ollama** (Optional): If you want to run LLMs completely locally. Download at [ollama.com](https://ollama.com/).

### General Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/aaramos/Epstein_Files_RAG
cd Epstein_Files_RAG

# Optional create a virtual environment
python -m venv venv
. venv/bin/activate

# install dependencies
pip install -r requirements.txt
```

### Environment Configuration
Copy the `.env.example` to `.env` and configure your providers:
```bash
cp .env.example .env
```
Fill in your API keys in `.env`:
- **Groq API**: Get yours at [console.groq.com](https://console.groq.com/).
- **OpenRouter API**: Get yours at [openrouter.ai](https://openrouter.ai/).
- **Ollama**: No key needed, just ensure it's running.

### Data Ingestion
The Epstein dataset is massive (>200GB). By default, the ingestion script downloads only the first **0.5 GB** chunk for testing.
```bash
python ingest.py
```
- **Estimated Time**: ~3-5 minutes for the first chunk (depending on your bandwidth).
- **Full Corpus**: Run `python ingest.py --all` or use `make download` and
  `make index`.

### Launch the Application
Start the Streamlit dashboard:
```bash
streamlit run app.py
# Mac/oMLX helper:
scripts/run_native.sh
```

---

## 📊 Dataset Info
- **Source**: [Nikity/Epstein-Files](https://huggingface.co/datasets/Nikity/Epstein-Files) on Hugging Face.
- **Format**: Apache Parquet files containing extracted text from investigative files.
- **Note**: The 0.5 GB limit (one parquet file) is used to ensure quick setup and low memory usage. The full dataset contains hundreds of thousands of documents.

## 🛡️ Guardrails
This application includes specialized system prompts to ensure the assistant stays strictly within the investigative context. It will refuse out-of-scope requests (like general knowledge or unrelated tasks) to maintain the integrity of the analysis.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
