# RAG Quickstart

Get started with Retrieval-Augmented Generation (RAG) using SecondBrain.

## Overview

RAG combines document retrieval with language models to provide context-aware responses.

## Setup

### 1. Install Dependencies

```bash
pip install secondbrain ollama
```

### 2. Configure Services

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017

# Ollama LLM
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2
```

### 3. Start Ollama

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull model
ollama pull llama2

# Start server
ollama serve
```

## Basic RAG Pipeline

### Ingest Documents

```bash
secondbrain ingest ./documents/ --recursive
```

### Query with Context

```python
from secondbrain.rag import RAGPipeline

# Initialize pipeline
pipeline = RAGPipeline(
    storage=storage,
    llm=OllamaLLM(model="llama2")
)

# Query
response = pipeline.query(
    "What are the key findings?",
    top_k=5
)

print(response)
```

## CLI Usage

### Search with Context

```bash
secondbrain rag-query "What is machine learning?" \
  --top-k 5 \
  --model llama2
```

### Conversation Mode

```bash
secondbrain rag-chat
> What is machine learning?
> How does it relate to AI?
```

## Advanced Usage

### Custom Prompt

```python
from secondbrain.rag import RAGPipeline

pipeline = RAGPipeline(
    storage=storage,
    llm=llm,
    prompt="""
    You are a helpful assistant. Use the following context to answer the question.
    
    Context:
    {context}
    
    Question: {question}
    
    Answer:
    """
)
```

### Streaming Response

```python
for chunk in pipeline.query_stream("Question"):
    print(chunk, end="", flush=True)
```

## Best Practices

### Document Preparation

- Use clear, well-structured documents
- Include relevant metadata
- Chunk documents appropriately

### Query Optimization

- Be specific in queries
- Use follow-up questions for clarification
- Adjust top_k for context length

### Performance

- Cache embeddings
- Use GPU for faster inference
- Batch queries when possible

## Troubleshooting

### LLM Connection Failed

**Solution**: Verify Ollama is running: `ollama list`

### Poor Response Quality

**Solutions**:
- Increase top_k for more context
- Try different LLM model
- Improve document quality

## See Also

- [User Guide](../user-guide/conversational-qa.md)
- [Async API](../developer-guide/async-api.md)
- [Examples](../examples/README.md)
