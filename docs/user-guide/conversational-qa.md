# Conversational Q&A with Documents

This guide explains how to use the conversational RAG (Retrieval-Augmented Generation) feature to have multi-turn conversations with your ingested documents using a local LLM.

## Overview

The `secondbrain chat` command enables you to:
- Ask questions about your documents in natural language
- Have multi-turn conversations with context preservation
- Get answers based on retrieved document chunks
- Use local LLMs for privacy and cost efficiency

Unlike the `search` command which returns ranked results, `chat` provides conversational responses that maintain context across multiple turns.

## Prerequisites

### 1. Configure LLM Provider

Configure your LLM provider in the `.env` file:

```bash
# For LiteLLM proxy or OpenAI-compatible servers
SECONDBRAIN_LLM_PROVIDER=openai
SECONDBRAIN_OPENAI_BASE_URL=http://your-llm-server:4000
SECONDBRAIN_OPENAI_API_KEY=your-api-key
SECONDBRAIN_LLM_MODEL=llama3.1:latest
```

See [RAG Quick Start](../getting-started/rag-quickstart.md) for detailed LLM setup instructions.

## Quick Start

### Basic Chat

Start a conversation with a single query:

```bash
secondbrain chat "What is secondbrain?"
```

The system will:
1. Retrieve relevant document chunks
2. Format them into context
3. Generate a response using your local LLM
4. Display the answer

### Interactive Mode

Enter interactive REPL mode for multi-turn conversations:

```bash
secondbrain chat
```

You can now:
- Ask follow-up questions that maintain context
- Use `/help` to see available commands
- Use `/quit` or `/exit` to leave

Example:
```
> What is secondbrain?
SecondBrain is a local document intelligence CLI tool...

> How does it store vectors?
It uses MongoDB for vector storage with sentence-transformers...

> What about security?
[Context-aware response about security features]

> /quit
```

## CLI Reference

### Command Syntax

```bash
secondbrain chat [QUERY] [OPTIONS]
```

### Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `QUERY` | Query text. If omitted, enters interactive mode | No |

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--session`, `-s` | Session ID for conversation continuity | `default` |
| `--top-k`, `-k` | Number of chunks to retrieve | `5` |
| `--temperature`, `-t` | LLM temperature (0.0-2.0) | `0.1` |
| `--model`, `-m` | Override default LLM model | (from config) |
| `--show-sources` | Display retrieved document chunks | `false` |
| `--list-sessions` | List all conversation sessions | `false` |
| `--history` | Show current session history | `false` |
| `--delete-session`, `-d` | Delete a session by ID | - |
| `--check-llm` | Verify LLM is accessible | `false` |

### Examples

**Single-turn query:**
```bash
secondbrain chat "Explain the architecture"
```

**With specific session:**
```bash
secondbrain chat --session project-review "What did we discuss about testing?"
```

**Show sources:**
```bash
secondbrain chat --show-sources "How does chunking work?"
```

**Custom temperature:**
```bash
secondbrain chat --temperature 0.7 "Be more creative in your response"
```

**List sessions:**
```bash
secondbrain chat --list-sessions
```

**Check LLM availability:**
```bash
secondbrain chat --check-llm
```

## Interactive Mode Commands

When in interactive mode (no query provided), use these commands:

| Command | Description |
|---------|-------------|
| `/quit`, `/exit` | Exit the chat |
| `/clear` | Clear conversation history |
| `/help` | Show available commands |
| `/history` | Show recent messages |
| `/session <id>` | Switch to a different session |

## Session Management

Sessions allow you to maintain conversation context across multiple queries.

### Create/Use Session

```bash
# Create or load session "project-a"
secondbrain chat --session project-a "Start of conversation"
secondbrain chat --session project-a "Follow-up question"
```

### List All Sessions

```bash
secondbrain chat --list-sessions
```

Output:
```
Sessions:
  - default (created: 2026-03-22 10:30, 5 messages)
  - project-a (created: 2026-03-22 11:15, 12 messages)
  - research (created: 2026-03-21 14:00, 3 messages)
```

### View Session History

```bash
secondbrain chat --session project-a --history
```

### Delete Session

```bash
secondbrain chat --delete-session project-a
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECONDBRAIN_LLM_PROVIDER` | LLM provider type | `openai` |
| `SECONDBRAIN_OPENAI_BASE_URL` | LLM server endpoint | (OpenAI) |
| `SECONDBRAIN_OPENAI_API_KEY` | API key for LLM server | (required) |
| `SECONDBRAIN_LLM_MODEL` | Default LLM model | `llama3.1:latest` |
| `SECONDBRAIN_LLM_TEMPERATURE` | Generation temperature | `0.1` |
| `SECONDBRAIN_LLM_MAX_TOKENS` | Max tokens to generate | `2048` |
| `SECONDBRAIN_LLM_TIMEOUT` | Request timeout (seconds) | `120` |
| `SECONDBRAIN_RAG_CONTEXT_WINDOW` | Recent messages to keep | `10` |

### Model Selection

Choose models based on your needs:

- **`llama3.1:latest`** (default): Good balance of speed and quality
- **`llama3.1`**: Better quality, larger
- **`mistral`**: Fast, good for general tasks
- **`codellama`**: Optimized for code-related questions

## Troubleshooting

### LLM Server Unavailable

**Problem:** Can't connect to LLM server

**Solutions:**
1. Verify LLM server is running
2. Check the endpoint: `SECONDBRAIN_OPENAI_BASE_URL`
3. Verify API key: `SECONDBRAIN_OPENAI_API_KEY`
4. Run: `secondbrain chat --check-llm`

### Model Not Found

**Problem:** Specified model isn't available

**Solutions:**
1. Verify model is available on your LLM server
2. Update config: `SECONDBRAIN_LLM_MODEL=llama3.1:latest`
3. Try a different model

### Slow responses

**Problem:** LLM generation takes too long

**Solutions:**
1. Use a smaller/faster model
2. Reduce max tokens: `SECONDBRAIN_LLM_MAX_TOKENS=1024`
3. Increase timeout: `SECONDBRAIN_LLM_TIMEOUT=180`

### No relevant documents found

**Problem:** Chat can't find answers in your documents

**Solutions:**
1. Ensure documents are ingested: `secondbrain ls`
2. Increase top-k: `secondbrain chat --top-k 10 "query"`
3. Re-index documents if needed

## Best Practices

### Temperature Settings

- **`0.1-0.3`**: Factual queries, document Q&A (recommended)
- **`0.5-0.7`**: Creative tasks, brainstorming
- **`0.8+`**: Highly creative, less predictable

### Context Window

- **`5-10`**: Short conversations, fast responses
- **`10-20`**: Medium-length discussions
- **`20+`**: Long research sessions, more memory usage

### Session Organization

- Use descriptive session IDs: `project-a`, `research-notes`, `code-review`
- Delete old sessions to free MongoDB space
- Use `--history` to review before continuing

## Next Steps

- See [RAG Quickstart](../getting-started/rag-quickstart.md) for initial setup
- See [Configuration Guide](../getting-started/configuration.md) for advanced settings
- See [Search Guide](search-guide.md) for traditional document search
