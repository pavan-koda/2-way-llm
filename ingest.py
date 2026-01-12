﻿import os, fitz, uuid
import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from config import *

class DatasetBuilder:
    def __init__(self):
        if torch.cuda.is_available():
            print(f"✅ GPU Detected: {torch.cuda.get_device_name(0)}")
        else:
            print("⚠️ GPU Not Detected, using CPU")
        self.embed_model = SentenceTransformer(EMBED_MODEL_NAME, device="cuda")
        self.client = QdrantClient(path=DB_PATH)
        if not self.client.collection_exists(COLLECTION_NAME):
            self.client.create_collection(COLLECTION_NAME, vectors_config=VectorParams(size=1024, distance=Distance.COSINE))

    def process_pdf(self, file_path):
        doc = fitz.open(file_path)
        doc_name = os.path.basename(file_path)
        doc_id = str(uuid.uuid4())[:8]
        points = []
        for i in range(0, len(doc), 2):
            window = doc[i : i + 2]
            text = " ".join([p.get_text() for p in window])
            vector = self.embed_model.encode(text).tolist()
            points.append(PointStruct(id=str(uuid.uuid4()), vector=vector, payload={
                "doc_name": doc_name, "text": text, "page_start": i+1, "page_end": min(i+2, len(doc))
            }))
        self.client.upsert(COLLECTION_NAME, points=points)
