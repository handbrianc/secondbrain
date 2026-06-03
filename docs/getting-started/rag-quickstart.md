# Conversational RAG Quick Start

Get up and running with conversational RAG (Retrieval-Augmented Generation) in 10 minutes. Ask questions about your documents using a local LLM.

## What is Conversational RAG?

Conversational RAG combines semantic search with large language models to provide contextual answers from your documents. Unlike simple keyword search, it:

- **Understands context**: Remembers previous questions in a conversation
- **Provides answers**: Generates natural language responses, not just document snippets
- **Shows sources**: Tells you which documents informed each answer
- **Runs locally**: Uses local LLMs for private, offline processing

Think of it as having a conversation with your document collection. Ask follow-up questions, get summarized answers, and trace responses back to their source material.

## Prerequisites

Before using conversational RAG, ensure you have:

- **Python 3.11+** - Check with `python --version`
- **MongoDB 8.0+** - Running locally or via Docker
- **SecondBrain installed** - Follow the [Installation Guide](installation.md)
- **Documents ingested** - Your documents must be in the vector database

If you haven't set these up yet, start with the [Quick Start Guide](quick-start.md).

## Setting Up a Local LLM

SecondBrain uses a local LLM for generating responses. You need to set up an LLM server and choose a model.

### Using LiteLLM Proxy

For production deployments, you can use a LiteLLM proxy server:

```bash
# Configure in your .env file
SECONDBRAIN_LLM_PROVIDER=openai
SECONDBRAIN_OPENAI_BASE_URL=http://your-litellm-server:4000
SECONDBRAIN_OPENAI_API_KEY=your-api-key
SECONDBRAIN_LLM_MODEL=Qwen/Qwen3.5-122B-A10B-FP8
```

### Using Local LLM Servers

For local development, you can run LLM servers like vLLM, LM Studio, or other OpenAI-compatible servers. Configure the endpoint in your `.env` file:

```bash
# Example configuration for local LLM server
SECONDBRAIN_LLM_PROVIDER=openai
SECONDBRAIN_OPENAI_BASE_URL=http://localhost:8080
SECONDBRAIN_OPENAI_API_KEY=your-local-key
```

Refer to your LLM server's documentation for installation and setup instructions.

### Verify LLM Setup

```bash
# Check if LLM server is accessible
secondbrain chat --check-llm

# You should see: ✓ LLM provider is available
```

## Selecting a Model

SecondBrain defaults to `llama3.1:latest` for local deployments, but you can configure any compatible model.

### Configure Model in .env

```bash
# Set your preferred model
SECONDBRAIN_LLM_MODEL=llama3.1:latest
```

### Alternative Models

You can use other models depending on your needs:

- `llama3.1` - More capable, larger (~4GB)
- `mistral` - Good balance (~4GB)
- `phi3` - Small and fast (~2GB)
- `gemma2` - Google's model (~2GB)

**Recommendation**: Start with `llama3.1:latest` for speed, switch to `llama3.1` or `mistral` for better quality if you have the resources.

### Verify Model is Available

```bash
# Check available models (depends on your LLM server)
# Consult your LLM server documentation for model listing
```

## First Chat Command

Now let's chat with your documents.

### Basic Single Question

```bash
# Ask a single question
secondbrain chat "What is this project about?"

# Example output:
# Answer:
# This project is a local document intelligence CLI tool called SecondBrain.
# It ingests documents, generates embeddings, and enables semantic search...
```

The command:
1. Searches your documents for relevant chunks
2. Sends them to the LLM with your question
3. Returns a natural language answer
4. Stores the conversation in a session

### Interactive Chat Mode

For multi-turn conversations:

```bash
# Start interactive chat (no query argument)
secondbrain chat

# You'll see:
# SecondBrain Interactive Chat
# ============================================================
# Session: default
# Type /quit to exit, /clear to clear history, /help for commands
#
# [you]: What is this project about?
# Assistant:
# This project is a local document intelligence CLI tool...
#
# [you]: How does it handle PDFs?
# Assistant:
# SecondBrain uses PyMuPDF to extract text from PDF files...
#
# [you]: /quit
```

### Show Sources

See which documents informed the answer:

```bash
# Show source documents
secondbrain chat "How does authentication work?" --show-sources

# Output includes:
# Answer:
# Authentication is handled via MongoDB URI configuration...
#
# Sources:
# [1] config.py (page 1): SECONDBRAIN_MONGO_URI=mongodb://...
# [2] README.md (page 1): MongoDB 8.0+ required...
```

### Use a Specific Model

Override the default model:

```bash
# Use a different model for this chat
secondbrain chat "Explain the architecture" --model llama3.1
```

### Adjust Response Quality

Control the "creativity" of responses:

```bash
# Lower temperature = more focused, factual responses
secondbrain chat "Summarize this" --temperature 0.1

# Higher temperature = more creative, varied responses
secondbrain chat "Suggest improvements" --temperature 0.7
```

Temperature ranges from 0.0 (deterministic) to 2.0 (very creative). Default is 0.1.

## Understanding Sessions

Sessions let you maintain conversation history across multiple questions.

### Default Session

If you don't specify a session, SecondBrain uses `default`:

```bash
# Both commands use the same session
secondbrain chat "What is RAG?"
secondbrain chat "How does it work?"  # Remembers first question
```

### Named Sessions

Create separate conversation threads:

```bash
# Start a new session for architecture questions
secondbrain chat --session architecture "Explain the data flow"

# Another session for installation issues
secondbrain chat --session troubleshooting "MongoDB connection failed"

# Each session maintains its own history
```

### List Sessions

See all your conversation sessions:

```bash
# List all sessions
secondbrain chat --list-sessions

# Output:
# Conversation Sessions
# ============================================================
#   default: 15 messages (created: 2025-03-20T14:30:00)
#   architecture: 3 messages (created: 2025-03-21T09:15:00)
#   troubleshooting: empty (created: 2025-03-21T11:45:00)
```

### View Session History

See the messages in a session:

```bash
# View history of a specific session
secondbrain chat --session architecture --history

# Output:
# Session History: architecture
# ============================================================
# User (2025-03-21 09:15:00): Explain the data flow
# Assistant (2025-03-21 09:15:02): The data flow starts with...
# User (2025-03-21 09:16:30): What about error handling?
# Assistant (2025-03-21 09:16:32): Error handling uses the circuit...
```

### Delete Sessions

Remove old conversations:

```bash
# Delete a session
secondbrain chat --delete-session troubleshooting

# Confirmation:
# Deleted session: troubleshooting
```

### How Sessions Work

- **In-memory cache**: Recent messages stored in RAM for fast access
- **MongoDB persistence**: All messages saved to `conversation_sessions` collection
- **Context window**: Defaults to 10 recent messages (configurable)
- **Automatic trimming**: Older messages removed when exceeding context window

Configuration in `.env`:

```bash
# Keep more context (default: 10)
SECONDBRAIN_RAG_CONTEXT_WINDOW=20
```

## Complete Example Workflow

Here's a typical workflow from start to finish:

```bash
# 1. Check LLM is available
secondbrain chat --check-llm
# Output: ✓ LLM provider is available
```

## Configuration Options

### Environment Variables

Configure RAG behavior in your `.env` file:

```bash
# LLM settings
SECONDBRAIN_LLM_PROVIDER=openai
SECONDBRAIN_OPENAI_BASE_URL=http://your-litellm-server:4000
SECONDBRAIN_OPENAI_API_KEY=your-api-key
SECONDBRAIN_LLM_MODEL=llama3.1:latest
SECONDBRAIN_LLM_TEMPERATURE=0.1
SECONDBRAIN_LLM_MAX_TOKENS=2048
SECONDBRAIN_LLM_TIMEOUT=120

# RAG settings
SECONDBRAIN_RAG_CONTEXT_WINDOW=10
```

### CLI Options Reference

| Option | Default | Description |
|--------|---------|-------------|
| `--session, -s` | `default` | Session ID for conversation |
| `--top-k, -k` | `5` | Number of chunks to retrieve |
| `--temperature, -t` | `0.1` | LLM temperature (0.0-2.0) |
| `--model, -m` | `llama3.1:latest` | LLM model name |
| `--show-sources` | `false` | Display retrieved sources |
| `--list-sessions` | `false` | List all sessions |
| `--history` | `false` | Show session history |
| `--delete-session, -d` | - | Delete a session |
| `--check-llm` | `false` | Check LLM availability |

## Troubleshooting

### LLM Unreachable

```bash
# Check if LLM is accessible
secondbrain chat --check-llm

# If not accessible, verify your configuration
# Check SECONDBRAIN_OPENAI_BASE_URL and SECONDBRAIN_OPENAI_API_KEY in .env
```

### Model Not Found

```bash
# Verify model is available on your LLM server
# Consult your LLM server documentation for model listing

# Or use a different model
secondbrain chat "question" --model mistral
```

### No Relevant Documents

If you get generic answers:

```bash
# Check if documents are ingested
secondbrain status

# Ingest more documents
secondbrain ingest /path/to/documents/

# Try a more specific query
secondbrain search "specific topic"
```

### Slow Responses

- Use a smaller model (`phi3`, `gemma2`)
- Reduce `--top-k` to retrieve fewer chunks
- Check system resources (CPU, RAM, disk I/O)

## Next Steps

Now that you're comfortable with conversational RAG:

- **[Configuration Guide](configuration.md)** - Deep dive into all settings
- **[User Guide](../user-guide/index.md)** - Complete usage reference
- **[CLI Reference](../user-guide/cli-reference.md)** - All commands and options
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions

## Quick Command Reference

```bash
# Single question
secondbrain chat "your question"

# Interactive chat
secondbrain chat

# With custom session
secondbrain chat --session my-session "question"

# Show sources
secondbrain chat "question" --show-sources

# List sessions
secondbrain chat --list-sessions

# Check LLM availability
secondbrain chat --check-llm

# Exit interactive mode
/quit
```

Happy chatting with your documents!
