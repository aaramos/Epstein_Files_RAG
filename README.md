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
cp .env.example .env
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python ingest.py --num-files 1
.venv/bin/python -m streamlit run app.py
```

For the full dataset:

```bash
.venv/bin/python ingest.py --all --download-only
.venv/bin/python ingest.py --all --skip-download --embedding-device mps
```

Or use the native helper:

```bash
EMBEDDING_DEVICE=auto scripts/index_full_native.sh
```

The ingester is resumable. It records completed parquet files in
`chroma_db/ingest_manifest.json`, streams parquet row batches to keep memory
bounded, and uses stable chunk IDs.

To check progress without importing the ML stack:

```bash
.venv/bin/python ingest.py --status --check-hub
# or
scripts/status.sh
```

To run a Mac readiness check:

```bash
scripts/doctor.sh
```

Useful ingestion tuning knobs:

- `--row-batch-size`: parquet rows to stream at once.
- `--batch-size`: chunks to embed/write to Chroma at once.
- `--embedding-device mps`: request Apple Silicon acceleration for native runs.
  If PyTorch cannot initialize MPS on the current macOS/runtime, the app falls
  back to CPU automatically.

### Docker
The app can run in Docker Compose and connect back to host oMLX:

```bash
docker compose up --build
```

The compose file mounts `./data`, `./chroma_db`, and your host
`~/.omlx/settings.json` as a read-only secret. Containers do not get Apple MPS
acceleration, so native Mac execution is preferred for high-throughput
embedding/indexing.

### macOS LaunchAgent Templates
Example LaunchAgent plists live in `launchd/`:

- `com.epstein-rag.app.plist.example` starts the Streamlit app.
- `com.epstein-rag.indexer.plist.example` runs the full native indexer.

Copy a template into `~/Library/LaunchAgents/`, remove the `.example` suffix,
then load it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<file>.plist`.
The templates use this checkout path:
`/Users/macstudio/Documents/RAG/Epstein_Files_RAG_macstudio`.

### 1. Prerequisites
- **Python 3.10+** (Recommend using a virtual environment).
- **Ollama** (Optional): If you want to run LLMs completely locally. Download at [ollama.com](https://ollama.com/).
- **Windows Users**: If you encounter DLL initialization errors with TensorFlow/Transformers, ensure you follow the installation steps below precisely, as the `requirements.txt` includes critical fixes for `torch` and `protobuf`.

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/AbhisumatK/Epstein_Files_RAG
cd Epstein_Files_RAG

# Optional create a virtual environment
python -m venv venv
.\venv\Scripts\activate  # On Windows

# install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the `.env.example` to `.env` and configure your providers:
```bash
cp .env.example .env
```
Fill in your API keys in `.env`:
- **Groq API**: Get yours at [console.groq.com](https://console.groq.com/).
- **OpenRouter API**: Get yours at [openrouter.ai](https://openrouter.ai/).
- **Ollama**: No key needed, just ensure it's running.

### 4. Data Ingestion
The Epstein dataset is massive (>200GB). By default, the ingestion script downloads only the first **0.5 GB** chunk for testing.
```bash
python ingest.py
```
- **Estimated Time**: ~3-5 minutes for the first chunk (depending on your bandwidth).
- **How to Tweaks**: Open `ingest.py` and change `num_files=1` to a higher number (e.g., `num_files=10` for ~5GB) to index more data.

### 5. Launch the Application
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
