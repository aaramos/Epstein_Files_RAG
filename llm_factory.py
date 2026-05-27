import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv()

def get_llm(provider=None, model_name=None):
    """
    Factory function to get the LLM based on provider.
    """
    provider = provider or os.getenv("LLM_PROVIDER", "OLLAMA").upper()
    
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
