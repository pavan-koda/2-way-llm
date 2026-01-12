import ollama
from pathlib import Path
from qdrant_client import QdrantClient, models
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from sentence_transformers import CrossEncoder

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "qdrant_data"
COLLECTION_NAME = "local_docs"
EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-large"
LLM_MODEL = "qwen2.5:7b-instruct"

print("Initializing AI Core Models...")

# Load Models (Global to avoid reloading per request)
# 1. Embedding Model for Vector Search
embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME, device="cpu")

# 2. Reranker for Precision (Top 30 -> Top 5)
reranker = CrossEncoder(RERANK_MODEL_NAME, device="cpu")

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
    
    # --- STEP 1: Vector Search ---
    query_vector = embed_model.get_query_embedding(query)
    
    search_result = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id",
                    match=models.MatchValue(value=doc_id)
                )
            ]
        ),
        limit=25 # Fetch a broad set of candidates
    )
    
    if not search_result:
        return "Information not found in the selected document."

    # --- STEP 2: Reranking ---
    # Create pairs of (query, document_text)
    passages = [(query, hit.payload["text"]) for hit in search_result]
    scores = reranker.predict(passages)
    
    # Sort by score (descending) and take Top 5
    top_indices = scores.argsort()[::-1][:5]
    top_hits = [search_result[i] for i in top_indices]
    
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
        "2. Follow with 'Evidence:'.\n"
        "3. Under Evidence, list exact quotes from the text that support your answer.\n"
        "4. Format quotes as: • \"<exact quote>\" (Page <number>)\n"
        "5. Do not make up quotes or page numbers."
    )
    
    user_prompt = f"Context:\n{context_str}\n\nQuestion: {query}"
    
    try:
        response = ollama.chat(model=LLM_MODEL, messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ])
        return response['message']['content']
    except Exception as e:
        return f"Error communicating with LLM: {str(e)}"
