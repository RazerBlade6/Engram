from pathlib import Path

import chromadb
from llama_index.core import Settings as LlamaSettings
from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.chroma import ChromaVectorStore

from backend.app.core.config import settings
from backend.app.rag.prompts import QA_SYSTEM_PROMPT, STUDY_NOTES_PROMPT

class RagEngine:
    def __init__(self) -> None:
        LlamaSettings.llm = OpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            system_prompt=QA_SYSTEM_PROMPT,
            temperature=0.1,
        )
        LlamaSettings.embed_model = OpenAIEmbedding(
            model=settings.openai_embed_model,
            api_key=settings.openai_api_key,
        )

        self.chroma_client = chromadb.PersistentClient(
            path=str(settings.chroma_persist_dir)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            settings.collection_name
        )
        self.vector_store = ChromaVectorStore(chroma_collection=self.collection)
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )

    def _index(self) -> VectorStoreIndex:
        return VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            storage_context=self.storage_context,
        )

    def ingest_pdf(self, pdf_path: Path) -> int:
        reader = SimpleDirectoryReader(
            input_files=[str(pdf_path)],
            filename_as_id=True,
        )
        documents = reader.load_data()

        for document in documents:
            document.metadata["source"] = pdf_path.name

        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=self.storage_context,
            show_progress=True,
        )
        return len(index.docstore.docs)

    def answer_question(self, question: str) -> tuple[str, list[str]]:
        query_engine = self._index().as_query_engine(
            similarity_top_k=5,
            response_mode=ResponseMode.COMPACT,
        )
        response = query_engine.query(question)
        return str(response), self._source_names(response.source_nodes)

    def generate_study_notes(self, topic: str | None = None) -> tuple[str, list[str]]:
        focus = topic or "the uploaded textbook material"
        prompt = f"{STUDY_NOTES_PROMPT}\n\nFocus: {focus}"

        query_engine = self._index().as_query_engine(
            similarity_top_k=10,
            response_mode=ResponseMode.TREE_SUMMARIZE,
        )
        response = query_engine.query(prompt)
        return str(response), self._source_names(response.source_nodes)

    @staticmethod
    def _source_names(source_nodes) -> list[str]:
        names: list[str] = []
        for source_node in source_nodes or []:
            source = source_node.node.metadata.get("source")
            if source and source not in names:
                names.append(source)
        return names


rag_engine = RagEngine()
