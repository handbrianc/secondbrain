# Conversational Q&A

Use SecondBrain for conversational question answering.

## Overview

Conversational Q&A allows you to chat with your documents using natural language.

## Setup

### Prerequisites

- SecondBrain installed
- Documents ingested
- LLM configured (Ollama or other)

### Configuration

```env
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2
```

## Basic Usage

### Single Question

```bash
secondbrain qna "What is machine learning?"
```

### With Context

```bash
secondbrain qna "Explain neural networks" --top-k 5
```

## Interactive Mode

### Start Chat

```bash
secondbrain qna --interactive
```

### Example Conversation

```
> What is machine learning?
Machine learning is a subset of artificial intelligence...

> How does it relate to deep learning?
Deep learning is a specialized form of machine learning...

> What are common applications?
Common applications include...
```

## Advanced Features

### Context Window

```bash
# Increase context
secondbrain qna "Question" --context-window 2000
```

### Temperature

```bash
# Control creativity
secondbrain qna "Question" --temperature 0.7
```

### System Prompt

```bash
# Custom system prompt
secondbrain qna "Question" --system-prompt "You are a helpful research assistant."
```

## Best Practices

### Effective Questions

- Be specific: "What are the benefits of X?" vs "Tell me about X"
- Ask follow-ups: Build on previous answers
- Provide context: "In the uploaded documents, what..."

### Response Quality

- Adjust top_k for more/less context
- Try different temperature settings
- Use specific queries

## Troubleshooting

### No Response

**Solution**: Check documents are ingested and LLM is running

### Poor Quality

**Solutions**:
- Increase top_k
- Refine question
- Try different model

### Slow Response

**Solutions**:
- Reduce top_k
- Use smaller context window
- Check LLM performance

## See Also

- [RAG Quickstart](../getting-started/rag-quickstart.md)
- [Search Guide](search-guide.md)
- [Examples](../examples/README.md)
