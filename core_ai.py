import ollama
from pathlib import Path
from qdrant_client import QdrantClient, models
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "qdrant_data"
COLLECTION_NAME = "local_docs"
EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"
LLM_MODEL = "qwen2.5:7b-instruct"

print("Initializing AI Core Models...")

# Load Models (Global to avoid reloading per request)
# 1. Embedding Model for Vector Search
embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME, device="cpu")

# 3. Database Client
client = QdrantClient(path=str(DB_PATH))

def retrieve_and_answer(query: str, doc_id: str):
    """
    Performs the RAG pipeline:
    1. Embed Query
    2. Vector Search (Filter by doc_id)
    3. Rerank Results
    4. Generate Answer with Citations
    """
    
    # Optimization: Handle simple greetings instantly to save time
    if query.strip().lower() in ["hi", "hello", "hey", "greetings", "hola"]:
        yield "Hello! I am ready to answer questions about your document."
        return

    # --- STEP 1: Vector Search ---
    query_vector = embed_model.get_query_embedding(query)
    
    query_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="doc_id",
                match=models.MatchValue(value=doc_id)
            )
        ]
    )
    
    try:
        search_result = client.search(collection_name=COLLECTION_NAME, query_vector=query_vector, query_filter=query_filter, limit=5)
    except AttributeError:
        # Fallback for client versions where 'search' might be missing or replaced by 'query_points'
        search_result = client.query_points(collection_name=COLLECTION_NAME, query=query_vector, query_filter=query_filter, limit=5).points
    
    if not search_result:
        yield "Information not found in the selected document."
        return

    top_hits = search_result
    
    # --- STEP 3: Context Construction ---
    # We wrap chunks in XML tags to help the LLM identify page numbers
    context_str = ""
    for hit in top_hits:
        page = hit.payload["page_number"]
        text = hit.payload["text"]
        context_str += f'<chunk page="{page}">\n{text}\n</chunk>\n\n'

    # --- STEP 4: LLM Generation ---
    system_prompt = (
        "You are a precise technical assistant. "
        "Answer the user's question using ONLY the provided context chunks. "
        "Do not use outside knowledge. "
        "If the answer is not in the chunks, say 'Information not found in the selected document.'\n\n"
        "FORMATTING RULES:\n"
        "1. Start with a clear 'Explanation:'.\n"
        "2. Use bullet points (*) for lists and bolding (**) for key terms in the explanation.\n"
        "3. Follow with 'Evidence:'.\n"
        "4. Under Evidence, list exact quotes from the text that support your answer.\n"
        "5. Format quotes as: • \"<exact quote>\" (Page <number>)\n"
        "6. Do not make up quotes or page numbers."
    )
    
    user_prompt = f"Context:\n{context_str}\n\nQuestion: {query}"
    
    try:
        stream = ollama.chat(model=LLM_MODEL, messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ], stream=True)
        for chunk in stream:
            yield chunk['message']['content']
    except Exception as e:
        yield f"Error communicating with LLM: {str(e)}"
