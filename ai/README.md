# LangChain RAG layer for Argus.
#
# langchain_rag.py      — split PDF pages, format context for prompts
# langchain_store.py    — PGVectorStore (argus_vectors table)
# langchain_chain.py    — retrieve + Gemini LCEL chain
# langchain_embeddings.py — GoogleGenerativeAIEmbeddings (3072-dim)
# langchain_llm.py      — ChatGoogleGenerativeAI
#
# Legacy ai/clients.py  — direct Gemini HTTP (retries, tests)
