from llama_cpp import Llama
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from config import *

class QASystem:
    def __init__(self):
        self.client = QdrantClient(path=DB_PATH)
        self.embed_model = SentenceTransformer(EMBED_MODEL_NAME, device="cpu")
        self.llm = Llama(model_path=QA_MODEL_PATH, n_ctx=4096, n_gpu_layers=16)

    def get_answer(self, question, doc_name):
        q_vec = self.embed_model.encode(question).tolist()
        res = self.client.search(COLLECTION_NAME, query_vector=q_vec, 
                                 query_filter=Filter(must=[FieldCondition(key="doc_name", match=MatchValue(value=doc_name))]), limit=5)
        context = "\n".join([f"(Pages {r.payload['page_start']}-{r.payload['page_end']}): {r.payload['text']}" for r in res])
        prompt = f"Answer using ONLY context.\nContext: {context}\nQuestion: {question}\nFormat: Explanation then Evidence."
        return self.llm(prompt, max_tokens=1024)["choices"][0]["text"]
