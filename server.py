import os
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
    """Lists PDFs currently in the documents folder."""
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
