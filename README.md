# ScholarRAG

A textbook-focused RAG starter project using:

- Backend: FastAPI
- RAG Framework: LlamaIndex
- Embeddings: OpenAI
- Vector DB: Chroma
- LLM: GPT-4o
- Frontend: Streamlit

The system is designed to answer questions and generate study notes using only the uploaded textbook material.

## Setup

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create your local environment file:

```powershell
Copy-Item .env.example .env
```

4. Edit `.env` and add your OpenAI API key:

```text
OPENAI_API_KEY=sk-...
```

## Run

Start the backend:

```powershell
uvicorn backend.app.main:app --reload --port 8000
```

In another terminal, start the frontend:

```powershell
streamlit run frontend/streamlit_app.py
```

Open the Streamlit URL printed in your terminal.

## API Endpoints

- `GET /health` - check backend status
- `POST /api/upload` - upload and index a PDF textbook
- `POST /api/ask` - answer a question from uploaded textbooks only
- `POST /api/study-notes` - generate study notes from uploaded textbooks only

## Important Behavior

The prompt templates explicitly instruct the model to answer only from retrieved textbook context. If the answer is not supported by the uploaded material, the system should say it cannot answer from the textbooks.

For production use, add authentication, upload validation, background ingestion jobs, better citation formatting, and tests around retrieval behavior.
