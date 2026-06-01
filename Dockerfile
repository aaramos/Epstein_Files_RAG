FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USE_TORCH=1 \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers

WORKDIR /app
ARG PIP_CONSTRAINT_FILE=""

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt constraints-macos-arm64.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && if [ -n "$PIP_CONSTRAINT_FILE" ]; then \
         pip install --no-cache-dir -r requirements.txt -c "$PIP_CONSTRAINT_FILE"; \
       else \
         pip install --no-cache-dir -r requirements.txt; \
       fi

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
