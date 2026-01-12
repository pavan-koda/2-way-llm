import os
import venv

# --- CONFIGURATION ---
# Target directory for the project
BASE_DIR = os.path.join(os.path.expanduser("~"), "local_ai_system")

# File Contents Definitions

REQUIREMENTS_TXT = """fastapi
uvicorn
python-multipart
qdrant-client
llama-index-core
llama-index-embeddings-huggingface
llama-index-readers-file
pymupdf
sentence-transformers
ollama
torch
transformers
accelerate
"""

INGEST_PY = """import os
import glob
import uuid
import torch
import fitz  # PyMuPDF
from pathlib import Path
from llama_index.core import Document
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models

# --- CONFIGURATION ---
# Paths relative to where this script is run
BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "documents"
DB_PATH = BASE_DIR / "qdrant_data"
COLLECTION_NAME = "local_docs"
EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"

def ensure_paths():
    DOCS_DIR.mkdir(exist_ok=True)
    DB_PATH.mkdir(exist_ok=True)

def load_pdf_content(file_path, doc_id):
    \"\"\"
    Extracts text from PDF while preserving page numbers.
    Returns a list of LlamaIndex Document objects (one per page).
    \"\"\"
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        print(f"Error opening {file_path}: {e}")
        return []

    documents = []
    print(f"  - Reading {os.path.basename(file_path)}...")
    
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        # Basic cleaning: collapse whitespace
        text = " ".join(text.split())
        
        if len(text) < 20: continue  # Skip empty/noise pages
        
        # We create a Document per page to maintain strict page mapping
        documents.append(
            Document(
                text=text,
                metadata={
                    "doc_id": doc_id,
                    "doc_name": os.path.basename(file_path),
                    "page_number": page_num + 1
                }
            )
        )
    return documents

def main():
    ensure_paths()
    print("--- STARTING INGESTION ---")
    
    # 1. Initialize Embedding Model (Local)
    # This handles the "Semantic" part of the chunking
    print("Loading Embedding Model (bge-large-en-v1.5)...")
    if torch.cuda.is_available():
        print(f"✅ GPU Detected: {torch.cuda.get_device_name(0)}")
        device_type = "cuda"
    else:
        print("⚠️ GPU Not Detected, using CPU")
        device_type = "cpu"
    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME, device=device_type)
    
    # 2. Initialize Qdrant (Local Vector DB)
    client = QdrantClient(path=str(DB_PATH))
    
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE),
        )
        # Create payload index for fast filtering by doc_id (CRITICAL for isolation)
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="doc_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    # 3. Process Files
    pdf_files = glob.glob(str(DOCS_DIR / "*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {DOCS_DIR.absolute()}. Please add some files.")
        return

    # Semantic Splitter: Groups sentences that are semantically similar
    splitter = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model
    )

    for file_path in pdf_files:
        # Create a safe ID
        doc_id = os.path.basename(file_path).replace(" ", "_")
        
        # Check if doc exists to avoid re-ingestion
        existing_count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=models.Filter(
                must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
            )
        ).count

        if existing_count > 0:
            print(f"Skipping {doc_id} (already ingested)")
            continue

        raw_docs = load_pdf_content(file_path, doc_id)
        if not raw_docs:
            continue

        print(f"  - Chunking {len(raw_docs)} pages semantically...")
        try:
            nodes = splitter.get_nodes_from_documents(raw_docs)
        except Exception as e:
            print(f"Error chunking {file_path}: {e}")
            continue
        
        points = []
        print(f"  - Embedding {len(nodes)} chunks...")
        for node in nodes:
            vector = embed_model.get_text_embedding(node.get_content())
            
            # Metadata payload
            payload = {
                "doc_id": doc_id,
                "doc_name": node.metadata["doc_name"],
                # If a chunk spans pages, we take the start page
                "page_number": node.metadata.get("page_number", 0),
                "text": node.get_content(),
                "chunk_id": str(uuid.uuid4())
            }
            
            points.append(models.PointStruct(
                id=payload["chunk_id"],
                vector=vector,
                payload=payload
            ))
        
        # Batch Upsert
        if points:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"  - Success: Ingested {len(points)} chunks for {doc_id}")

    print("--- INGESTION COMPLETE ---")

if __name__ == "__main__":
    main()
"""

CORE_AI_PY = """import ollama
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
    \"\"\"
    Performs the RAG pipeline:
    1. Embed Query
    2. Vector Search (Filter by doc_id)
    3. Rerank Results
    4. Generate Answer with Citations
    \"\"\"
    
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
        context_str += f'<chunk page="{page}">\\n{text}\\n</chunk>\\n\\n'

    # --- STEP 4: LLM Generation ---
    system_prompt = (
        "You are a precise technical assistant. "
        "Answer the user's question using ONLY the provided context chunks. "
        "Do not use outside knowledge. "
        "If the answer is not in the chunks, say 'Information not found in the selected document.'\\n\\n"
        "FORMATTING RULES:\\n"
        "1. Start with a clear 'Explanation:'.\\n"
        "2. Follow with 'Evidence:'.\\n"
        "3. Under Evidence, list exact quotes from the text that support your answer.\\n"
        "4. Format quotes as: • \\"<exact quote>\\" (Page <number>)\\n"
        "5. Do not make up quotes or page numbers."
    )
    
    user_prompt = f"Context:\\n{context_str}\\n\\nQuestion: {query}"
    
    try:
        response = ollama.chat(model=LLM_MODEL, messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ])
        return response['message']['content']
    except Exception as e:
        return f"Error communicating with LLM: {str(e)}"
"""

SERVER_PY = """import os
import glob
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from core_ai import retrieve_and_answer

app = FastAPI()

# Mount static files for the UI
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

class ChatRequest(BaseModel):
    doc_id: str
    query: str

class ChatResponse(BaseModel):
    answer: str

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

@app.get("/api/documents")
async def list_documents():
    \"\"\"Lists PDFs currently in the documents folder.\"\"\"
    doc_path = str(BASE_DIR / "documents" / "*.pdf")
    files = glob.glob(doc_path)
    # Return list of dicts: [{'id': 'filename', 'name': 'filename'}]
    return [{"id": os.path.basename(f).replace(" ", "_"), "name": os.path.basename(f)} for f in files]

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    print(f"Querying {request.doc_id}: {request.query}")
    try:
        answer = retrieve_and_answer(request.query, request.doc_id)
        return ChatResponse(answer=answer)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("Server running at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Local AI Assistant</title>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<div class="app-container">
    <aside class="sidebar">
        <h2>Documents</h2>
        <div class="select-container">
            <select id="doc-select">
                <option value="" disabled selected>Loading...</option>
            </select>
        </div>
        <div class="status-panel">
            <p>Status: <span id="system-status">Ready</span></p>
            <p class="note">Local Mode (Offline)</p>
        </div>
    </aside>
    <main class="chat-interface">
        <div class="chat-header"><h1 id="chat-title">Select a document</h1></div>
        <div id="chat-history" class="chat-history">
             <div class="message system">Welcome. Please select a document to begin.</div>
        </div>
        <div class="input-area">
            <textarea id="user-input" placeholder="Ask a question..." rows="1"></textarea>
            <button id="send-btn">Send</button>
        </div>
    </main>
</div>
<script src="/static/script.js"></script>
</body>
</html>"""

STYLES_CSS = """:root { --bg: #1e1e2e; --sidebar: #181825; --text: #cdd6f4; --accent: #89b4fa; --user-msg: #313244; --border: #45475a; }
body { margin: 0; font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }
.app-container { display: flex; height: 100%; }
.sidebar { width: 260px; background: var(--sidebar); padding: 20px; display: flex; flex-direction: column; border-right: 1px solid var(--border); }
.sidebar h2 { color: var(--accent); margin-top: 0; }
select { width: 100%; padding: 10px; background: var(--user-msg); color: white; border: 1px solid var(--border); border-radius: 4px; margin-top: 10px; }
.status-panel { margin-top: auto; font-size: 0.85rem; opacity: 0.7; }
.chat-interface { flex: 1; display: flex; flex-direction: column; }
.chat-header { padding: 15px 20px; border-bottom: 1px solid var(--border); }
.chat-history { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
.message { max-width: 80%; padding: 15px; border-radius: 8px; line-height: 1.5; }
.message.user { align-self: flex-end; background: var(--accent); color: #111; }
.message.ai { align-self: flex-start; background: var(--user-msg); white-space: pre-wrap; border: 1px solid var(--border); }
.message.system { align-self: center; background: transparent; color: #888; font-style: italic; }
.evidence-block { margin-top: 10px; padding: 10px; background: rgba(0,0,0,0.2); border-left: 3px solid var(--accent); font-size: 0.9em; }
.input-area { padding: 20px; border-top: 1px solid var(--border); display: flex; gap: 10px; }
textarea { flex: 1; padding: 12px; background: var(--user-msg); color: white; border: 1px solid var(--border); resize: none; border-radius: 4px; outline: none; }
button { padding: 0 20px; background: var(--accent); border: none; cursor: pointer; font-weight: bold; border-radius: 4px; }
button:disabled { opacity: 0.5; }"""

SCRIPT_JS = """const docSelect = document.getElementById('doc-select');
const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const statusLabel = document.getElementById('system-status');
const chatTitle = document.getElementById('chat-title');
let currentDocId = null;

async function loadDocs() {
    try {
        const res = await fetch('/api/documents');
        const docs = await res.json();
        docSelect.innerHTML = '<option value="" disabled selected>Select a Document</option>';
        docs.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.id;
            opt.textContent = d.name;
            docSelect.appendChild(opt);
        });
    } catch (e) { console.error(e); statusLabel.textContent = "Error loading docs"; }
}

docSelect.addEventListener('change', (e) => {
    currentDocId = e.target.value;
    chatTitle.textContent = e.target.options[e.target.selectedIndex].text;
    chatHistory.innerHTML = '';
    addMessage("System", `Document loaded. Ask a question.`);
});

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || !currentDocId) return;
    
    addMessage("User", text);
    userInput.value = '';
    userInput.disabled = true;
    sendBtn.disabled = true;
    statusLabel.textContent = "Thinking...";

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ doc_id: currentDocId, query: text })
        });
        const data = await res.json();
        addMessage("AI", data.answer);
    } catch (e) {
        addMessage("System", "Error connecting to server.");
    } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        statusLabel.textContent = "Ready";
        userInput.focus();
    }
}

function addMessage(role, text) {
    const div = document.createElement('div');
    div.className = `message ${role.toLowerCase()}`;
    
    if (role === "AI" && text.includes("Evidence:")) {
        const parts = text.split("Evidence:");
        const explanation = parts[0].replace("Explanation:", "").trim();
        const evidence = parts[1].trim();
        div.innerHTML = `<strong>Explanation:</strong><br>${explanation}<div class="evidence-block"><strong>Evidence:</strong><br>${evidence.replace(/\\n/g, '<br>')}</div>`;
    } else {
        div.textContent = text;
    }
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => { if(e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }});
loadDocs();"""

START_APP_SH = """#!/bin/bash

# Define project directory
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors
GREEN='\\033[0;32m'
BLUE='\\033[0;34m'
YELLOW='\\033[1;33m'
RED='\\033[0;31m'
NC='\\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Local AI System - Startup Script     ${NC}"
echo -e "${BLUE}========================================${NC}"

# 1. Navigate to project directory
if [ -d "$BASE_DIR" ]; then
    cd "$BASE_DIR"
    echo -e "${GREEN}✅ Directory found: $BASE_DIR${NC}"
else
    echo -e "${RED}❌ Error: Directory $BASE_DIR not found.${NC}"
    exit 1
fi

# 2. Activate Virtual Environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo -e "${GREEN}✅ Virtual Environment Activated${NC}"
else
    echo -e "${RED}❌ Error: venv not found.${NC}"
    exit 1
fi

# 3. Check AI Models (Ollama)
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}❌ Error: Ollama is not installed. Please install it from https://ollama.com/${NC}"
    exit 1
fi

if ! ollama list | grep -q "qwen2.5:7b-instruct"; then
    echo -e "${BLUE}📥 Downloading LLM (qwen2.5:7b-instruct)...${NC}"
    ollama pull qwen2.5:7b-instruct
else
    echo -e "${GREEN}✅ LLM (Qwen) found.${NC}"
fi

# 4. Check for Documents
count=$(ls documents/*.pdf 2>/dev/null | wc -l)
if [ "$count" -eq "0" ]; then
    echo -e "${YELLOW}⚠️  Warning: No PDFs found in 'documents' folder.${NC}"
else
    echo -e "${GREEN}📄 Found $count PDF(s).${NC}"
fi

# 5. Ingestion Prompt
echo ""
read -p "❓ Run ingestion? (y/N): " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🚀 Starting Ingestion...${NC}"
    python ingest.py
    echo -e "${GREEN}✅ Ingestion Finished.${NC}"
else
    echo -e "${YELLOW}⏩ Skipping Ingestion.${NC}"
fi

# 6. Start Server
echo ""
echo -e "${BLUE}🚀 Starting Web Server...${NC}"
echo -e "   Access at: ${GREEN}http://localhost:8000${NC}"
echo -e "${BLUE}========================================${NC}"
python server.py
"""

def create_project_structure():
    # 1. Create Base Directory
    if not os.path.exists(BASE_DIR):
        try:
            os.makedirs(BASE_DIR)
            print(f"Created base directory: {BASE_DIR}")
        except OSError as e:
            print(f"Error creating directory {BASE_DIR}: {e}")
            print("Please check permissions or try running as Administrator.")
            return

    # 2. Create Subdirectories
    subdirs = ["documents", "static", "qdrant_data"]
    for subdir in subdirs:
        path = os.path.join(BASE_DIR, subdir)
        os.makedirs(path, exist_ok=True)

    # 3. Write Files
    files_to_write = {
        "requirements.txt": REQUIREMENTS_TXT,
        "ingest.py": INGEST_PY,
        "core_ai.py": CORE_AI_PY,
        "server.py": SERVER_PY,
        os.path.join("static", "index.html"): INDEX_HTML,
        os.path.join("static", "styles.css"): STYLES_CSS,
        os.path.join("static", "script.js"): SCRIPT_JS,
        "start_app.sh": START_APP_SH
    }

    for filename, content in files_to_write.items():
        file_path = os.path.join(BASE_DIR, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created file: {file_path}")

    # Make start_app.sh executable
    st_path = os.path.join(BASE_DIR, "start_app.sh")
    if os.path.exists(st_path):
        os.chmod(st_path, 0o755)

    # 4. Create Virtual Environment
    venv_dir = os.path.join(BASE_DIR, "venv")
    if not os.path.exists(venv_dir):
        print(f"Creating virtual environment at: {venv_dir}")
        venv.create(venv_dir, with_pip=True)

    print("\n" + "="*50)
    print("SETUP COMPLETE")
    print("="*50)
    print(f"Project created at: {BASE_DIR}")
    print("\nNEXT STEPS:")
    print(f"1. Open a terminal and navigate to the folder:")
    print(f"   cd \"{BASE_DIR}\"")
    print("2. Activate the virtual environment:")
    print("   source venv/bin/activate  (Or just run ./start_app.sh)")
    print("3. Install dependencies:")
    print("   pip install -r requirements.txt")
    print("4. Add your PDFs to the 'documents' folder.")
    print("5. Run the system:")
    print("   ./start_app.sh")

if __name__ == "__main__":
    create_project_structure()
