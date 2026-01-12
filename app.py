import streamlit as st
import os
from ingest import DatasetBuilder
from qa_engine import QASystem
from config import *

st.title("Offline PDF Expert")
@st.cache_resource
def init(): return DatasetBuilder(), QASystem()
builder, qa = init()

with st.sidebar:
    up = st.file_uploader("Upload PDF", type="pdf")
    if st.button("Ingest") and up:
        path = os.path.join(PDF_INPUT_DIR, up.name)
        with open(path, "wb") as f: f.write(up.getbuffer())
        builder.process_pdf(path); st.success("Indexed!")

scroll = builder.client.scroll(COLLECTION_NAME, limit=100)
docs = list(set([p.payload['doc_name'] for p in scroll[0]]))
sel = st.selectbox("Select Document", docs)
if sel:
    q = st.text_input("Ask Question")
    if q: st.markdown(qa.get_answer(q, sel))
