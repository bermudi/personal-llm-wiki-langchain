# LangChain + Deep Agents Development Guide

This project uses skills that contain up-to-date patterns and working reference scripts.

## Getting Started
- **framework-selection** - Invoke when choosing between LangChain, LangGraph, and Deep Agents
- **langchain-dependencies** - Invoke before installing packages or when resolving version issues (Python + TypeScript)

### LangChain Skills
- **langchain-fundamentals** - Invoke for create_agent, @tool decorator, middleware patterns
- **langchain-rag** - Invoke for RAG pipelines, vector stores, embeddings
- **langchain-middleware** - Invoke for structured output with Pydantic

### LangGraph Skills
- **langgraph-fundamentals** - Invoke for StateGraph, state schemas, edges, Command, Send, invoke, streaming, error handling
- **langgraph-persistence** - Invoke for checkpointers, thread_id, time travel, memory, subgraph scoping
- **langgraph-human-in-the-loop** - Invoke for interrupts, human review, error handling, approval workflows

### Deep Agents Skills
- **deep-agents-core** - Invoke for Deep Agents harness architecture
- **deep-agents-memory** - Invoke for long-term memory with StoreBackend
- **deep-agents-orchestration** - Invoke for multi-agent coordination

## Environment Setup

Required environment variables:
```bash
POE_API_KEY           # Chat completions — uses your Poe subscription credits
OPENROUTER_API_KEY    # Embeddings — cheap pay-as-you-go (~$0.02/1M tokens)

# Optional overrides
WIKI_MODEL            # Default: gpt-5.4-mini
WIKI_CHAT_BASE_URL    # Default: https://api.poe.com/v1
WIKI_EMBED_MODEL      # Default: perplexity/pplx-embed-v1-4b
WIKI_EMBED_BASE_URL   # Default: https://openrouter.ai/api/v1
WIKI_REASONING_EFFORT # Default: low
WIKI_USE_RESPONSES_API # Default: false (Responses API breaks multi-turn tool calls on Poe)
```

