# AI layer for Argus

- `chunking.py` — junk filter, chapter map, split PDF pages, format prompt context
- `vector_store.py` — PGVectorStore (`argus_vectors`) with batched embed + 429 pause
- `study_generate.py` — chapter-scoped quiz / flashcards / summary via Gemini
- `embeddings.py` — GoogleGenerativeAIEmbeddings (3072-dim)
- `llm.py` — ChatGoogleGenerativeAI wrapper
- `clients.py` — direct Gemini HTTP (retries, tests)
