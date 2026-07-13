import os

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="ScholarRAG", page_icon=":books:", layout="wide")

st.title("ScholarRAG")
st.caption("Upload textbooks, ask grounded questions, and generate study notes.")


def show_sources(sources: list[str]) -> None:
    if sources:
        st.markdown("**Sources**")
        for source in sources:
            st.write(f"- {source}")


with st.sidebar:
    st.header("Textbooks")
    uploaded_file = st.file_uploader("Upload a PDF textbook", type=["pdf"])

    if uploaded_file and st.button("Index textbook", type="primary"):
        with st.spinner("Uploading and indexing..."):
            response = requests.post(
                f"{BACKEND_URL}/api/upload",
                files={
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        "application/pdf",
                    )
                },
                timeout=300,
            )

        if response.ok:
            payload = response.json()
            st.success(
                f"Indexed {payload['filename']} "
                f"({payload['indexed_nodes']} nodes)."
            )
        else:
            st.error(response.text)


ask_tab, notes_tab = st.tabs(["Ask", "Study Notes"])

with ask_tab:
    question = st.text_area("Question", height=120)

    if st.button("Ask", type="primary", disabled=not question.strip()):
        with st.spinner("Searching textbook context..."):
            response = requests.post(
                f"{BACKEND_URL}/api/ask",
                json={"question": question},
                timeout=120,
            )

        if response.ok:
            payload = response.json()
            st.markdown(payload["answer"])
            show_sources(payload["sources"])
        else:
            st.error(response.text)

with notes_tab:
    topic = st.text_input("Optional topic or chapter focus")

    if st.button("Generate notes", type="primary"):
        with st.spinner("Building notes from retrieved textbook context..."):
            response = requests.post(
                f"{BACKEND_URL}/api/study-notes",
                json={"topic": topic or None},
                timeout=180,
            )

        if response.ok:
            payload = response.json()
            st.markdown(payload["notes"])
            show_sources(payload["sources"])
        else:
            st.error(response.text)
