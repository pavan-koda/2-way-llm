﻿import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_INPUT_DIR = os.path.join(BASE_DIR, "pdfs")
DB_PATH = os.path.join(BASE_DIR, "qdrant_db")
COLLECTION_NAME = "local_docs"
INGEST_MODEL_PATH = os.path.join(BASE_DIR, "models", "qwen2.5-14b-instruct-q4_k_m.gguf")
QA_MODEL_PATH = os.path.join(BASE_DIR, "models", "qwen2.5-7b-instruct-q4_k_m.gguf")
EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"
