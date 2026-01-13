import os
import glob
import shutil
import uuid
import time
import fitz  # PyMuPDF
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from llama_index.core import Document
from llama_index.core.node_parser import SemanticSplitterNodeParser
from qdrant_client import models
from core_ai import retrieve_and_answer, embed_model, client, COLLECTION_NAME

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events."""
    # 1. Ensure documents directory exists
    docs_dir = BASE_DIR / "documents"
    if not docs_dir.exists():
        docs_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {docs_dir}")

    # 2. Ensure Vector DB Collection exists
    if not client.collection_exists(COLLECTION_NAME):
        print(f"Creating collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE),
        )
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="doc_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    yield

app = FastAPI(lifespan=lifespan)

# Mount static files for the UI
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

class ChatRequest(BaseModel):
    doc_id: str
    query: str

class ChatResponse(BaseModel):
    answer: str

def load_pdf_content(file_path, doc_id):
    """Extracts text from PDF for ingestion."""
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        print(f"Error opening {file_path}: {e}")
        return []

    documents = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        text = " ".join(text.split())
        if len(text) < 20: continue
        
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

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

@app.get("/upload")
async def upload_page():
    """Serves the dedicated upload UI."""
    return FileResponse('static/upload.html')

@app.get("/api/documents")
async def list_documents():
    """Lists PDFs currently in the documents folder."""
    doc_path = str(BASE_DIR / "documents" / "*.pdf")
    files = glob.glob(doc_path)
    # Return list of dicts: [{'id': 'filename', 'name': 'filename'}]
    return [{"id": os.path.basename(f).replace(" ", "_"), "name": os.path.basename(f)} for f in files]

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    print(f"Querying {request.doc_id}: {request.query}")
    start_time = time.time()
    try:
        answer = retrieve_and_answer(request.query, request.doc_id)
        
        duration = time.time() - start_time
        if duration < 60:
            time_msg = f"({duration:.2f} seconds)"
        else:
            time_msg = f"({duration / 60:.2f} minutes)"
            
        answer += f"\n\n_Response time: {time_msg}_"
        return ChatResponse(answer=answer)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """Uploads a PDF and ingests it immediately."""
    safe_name = os.path.basename(file.filename)
    save_path = BASE_DIR / "documents" / safe_name
    
    # 1. Save File
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 2. Ingest
    doc_id = safe_name.replace(" ", "_")
    
    # Check if exists in DB
    count = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
        )
    ).count
    
    if count > 0:
        return {"status": "exists", "filename": safe_name, "doc_id": doc_id}

    # Process
    raw_docs = load_pdf_content(str(save_path), doc_id)
    if not raw_docs:
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")

    splitter = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model
    )
    
    nodes = splitter.get_nodes_from_documents(raw_docs)
    points = []
    
    for node in nodes:
        vector = embed_model.get_text_embedding(node.get_content())
        payload = {
            "doc_id": doc_id,
            "doc_name": node.metadata["doc_name"],
            "page_number": node.metadata.get("page_number", 0),
            "text": node.get_content(),
            "chunk_id": str(uuid.uuid4())
        }
        points.append(models.PointStruct(id=payload["chunk_id"], vector=vector, payload=payload))
        
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        
    return {"status": "success", "filename": safe_name, "doc_id": doc_id}

if __name__ == "__main__":
    import uvicorn
    print("Server running at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
