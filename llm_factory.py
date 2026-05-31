import os
import json
from pathlib import Path
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv()


def _get_omlx_api_key():
    api_key = (
        os.getenv("MORNING_DISPATCH_MODEL_API_KEY")
        or os.getenv("OMLX_API_KEY")
        or os.getenv("LM_API_KEY")
        or os.getenv("ANTHROPIC_AUTH_TOKEN")
    )
    if api_key:
        return api_key

    settings_path = Path(os.getenv("OMLX_SETTINGS_PATH", "~/.omlx/settings.json")).expanduser()
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            return settings.get("auth", {}).get("api_key")
        except (OSError, json.JSONDecodeError):
            return None

    return None


def get_llm(provider=None, model_name=None):
    """
    Factory function to get the LLM based on provider.
    """
    provider = provider or os.getenv("LLM_PROVIDER", "OLLAMA").upper()
    
    if provider == "OMLX":
        api_key = _get_omlx_api_key()
        if not api_key:
            raise ValueError("oMLX API key not found. Set MORNING_DISPATCH_MODEL_API_KEY, OMLX_API_KEY, LM_API_KEY, or OMLX_SETTINGS_PATH.")
        base_url = os.getenv("MORNING_DISPATCH_MODEL_BASE_URL") or os.getenv("OMLX_BASE_URL", "http://127.0.0.1:1234/v1")
        model = model_name or os.getenv("OMLX_MODEL") or os.getenv("MORNING_DISPATCH_LIBRARIAN_MODEL", "Gemma4-MTP-26B-BF16")
        return ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base=base_url,
            model_name=model,
            temperature=0
        )

    if provider == "OLLAMA":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = model_name or "llama3"
        return ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0
        )
    
    elif provider == "GROQ":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment")
        model = model_name or "llama-3.3-70b-versatile"
        return ChatGroq(
            groq_api_key=api_key,
            model_name=model,
            temperature=0
        )
    
    elif provider == "OPENROUTER":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment")
        model = model_name or "meta-llama/llama-3-8b-instruct"
        return ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_name=model,
            temperature=0
        )
    
    else:
        raise ValueError(f"Unsupported provider: {provider}")

if __name__ == "__main__":
    # Test
    try:
        llm = get_llm("OLLAMA")
        print("Ollama LLM initialized")
    except Exception as e:
        print(f"Error initializing Ollama: {e}")
