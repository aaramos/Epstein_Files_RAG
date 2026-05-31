import os
os.environ["USE_TORCH"] = "1" # Force PyTorch, disable TensorFlow
import streamlit as st
import os
from dotenv import load_dotenv
from rag_chain import get_rag_chain

load_dotenv()


@st.cache_resource(show_spinner=False)
def get_cached_rag_chain(provider, model_name):
    return get_rag_chain(provider=provider, model_name=model_name)


# Page configuration
st.set_page_config(
    page_title="Epstein Files RAG Explorer",
    page_icon="logo.png",
    layout="wide"
)

# Sidebar
st.sidebar.title("Configuration")
providers = ["OMLX", "OLLAMA", "GROQ", "OPENROUTER"]
configured_provider = os.getenv("LLM_PROVIDER", "OMLX").upper()
provider = st.sidebar.selectbox(
    "Select LLM Provider",
    providers,
    index=providers.index(configured_provider) if configured_provider in providers else 0
)

# API Keys and Models
api_key = None
model_name = None

if provider == "OMLX":
    model_name = st.sidebar.text_input(
        "oMLX Model",
        value=os.getenv("OMLX_MODEL") or os.getenv("MORNING_DISPATCH_LIBRARIAN_MODEL", "Gemma4-MTP-26B-BF16")
    )
elif provider == "GROQ":
    api_key = st.sidebar.text_input("Groq API Key", type="password", value=os.getenv("GROQ_API_KEY", ""))
    model_name = st.sidebar.text_input("Groq Model", value="llama-3.3-70b-versatile")
elif provider == "OPENROUTER":
    api_key = st.sidebar.text_input("OpenRouter API Key", type="password", value=os.getenv("OPENROUTER_API_KEY", ""))
    model_name = st.sidebar.text_input("OpenRouter Model", value="meta-llama/llama-3-8b-instruct")
else:
    model_name = st.sidebar.text_input("Ollama Model", value="llama3")

# Set environment variables for the current session
if api_key:
    if provider == "GROQ":
        os.environ["GROQ_API_KEY"] = api_key
    elif provider == "OPENROUTER":
        os.environ["OPENROUTER_API_KEY"] = api_key

# Main UI
col1, col2 = st.columns([1, 10])
with col1:
    st.image("logo.png", width=80)
with col2:
    st.title("Epstein Files RAG Explorer")
st.markdown("Query the unsealed Epstein court documents using open-source RAG.")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("citations"):
            with st.expander("View Citations"):
                for i, doc in enumerate(message["citations"]):
                    st.markdown(f"**Source {i+1}:** {doc['source']}")
                    st.markdown(f"**Original File:** {doc['file']}")
                    st.code(doc['content'][:500] + "...")

# Starter Questions
if not st.session_state.messages:
    st.markdown("### 🔍 Suggested Questions")
    questions = [
        "Who are the prominent individuals mentioned in the flight logs?",
        "What is the name of the aircraft used by Epstein?",
        "Which countries has Jeffery Epstein visited?",
        "List the documents related to the victims' depositions."
    ]
    
    cols = st.columns(2)
    for i, q in enumerate(questions):
        if cols[i % 2].button(q, use_container_width=True):
            # Simulate user input
            st.session_state.messages.append({"role": "user", "content": q})
            
            with st.chat_message("user"):
                st.markdown(q)
            
            with st.chat_message("assistant"):
                with st.spinner("Analyzing documents..."):
                    try:
                        chain = get_cached_rag_chain(provider, model_name)
                        response = chain.invoke({"input": q})
                        answer = response["answer"]
                        context = response["context"]
                        st.markdown(answer)
                        if context:
                            with st.expander("View Citations"):
                                for j, doc in enumerate(context):
                                    st.markdown(f"**Source {j+1}:** {doc.metadata.get('source', 'Unknown')}")
                                    st.markdown(f"**Original File:** {doc.metadata.get('original_filename', 'Unknown')}")
                                    st.code(doc.page_content[:500] + "...")
                        # Format citations for storage
                        citations = [
                            {
                                "source": doc.metadata.get('source', 'Unknown'),
                                "file": doc.metadata.get('original_filename', 'Unknown'),
                                "content": doc.page_content
                            } for doc in context
                        ] if context else []
                        
                        st.session_state.messages.append({"role": "assistant", "content": answer, "citations": citations})
                        st.rerun() # Refresh to hide starter questions
                    except Exception as e:
                        st.error(f"Error: {e}")

# User Input
if prompt := st.chat_input("Ask a question about the Epstein documents..."):
    # Clear session if provider/model changed? (Simplified here)
    
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Analyzing documents..."):
            try:
                # Initialize chain (ideally cached, but simplified here)
                chain = get_cached_rag_chain(provider, model_name)
                
                # Run query
                response = chain.invoke({"input": prompt})
                
                answer = response["answer"]
                context = response["context"]
                
                # Display answer
                st.markdown(answer)
                
                # Display citations
                if context:
                    with st.expander("View Citations"):
                        for i, doc in enumerate(context):
                            st.markdown(f"**Source {i+1}:** {doc.metadata.get('source', 'Unknown')}")
                            st.markdown(f"**Original File:** {doc.metadata.get('original_filename', 'Unknown')}")
                            st.code(doc.page_content[:500] + "...")
                
                # Format citations for storage
                citations = [
                    {
                        "source": doc.metadata.get('source', 'Unknown'),
                        "file": doc.metadata.get('original_filename', 'Unknown'),
                        "content": doc.page_content
                    } for doc in context
                ] if context else []
                
                # Add assistant message to history
                st.session_state.messages.append({"role": "assistant", "content": answer, "citations": citations})
                
            except Exception as e:
                st.error(f"Error: {e}")
