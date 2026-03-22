# Conversational RAG Quick Start

Get up and running with conversational RAG (Retrieval-Augmented Generation) in 10 minutes. Ask questions about your documents using a local LLM.

## What is Conversational RAG?

Conversational RAG combines semantic search with large language models to provide contextual answers from your documents. Unlike simple keyword search, it:

- **Understands context**: Remembers previous questions in a conversation
- **Provides answers**: Generates natural language responses, not just document snippets
- **Shows sources**: Tells you which documents informed each answer
- **Runs locally**: Uses Ollama for private, offline LLM processing

Think of it as having a conversation with your document collection. Ask follow-up questions, get summarized answers, and trace responses back to their source material.

## Prerequisites

Before using conversational RAG, ensure you have:

- **Python 3.11+** - Check with `python --version`
- **MongoDB 8.0+** - Running locally or via Docker
- **SecondBrain installed** - Follow the [Installation Guide](installation.md)
- **Documents ingested** - Your documents must be in the vector database

If you haven't set these up yet, start with the [Quick Start Guide](quick-start.md).

## Installing Ollama

Ollama is a local LLM server that runs models on your machine. SecondBrain uses it for generating conversational responses.

### macOS

```bash
# Install via Homebrew
brew install ollama

# Or download from ollama.ai
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve
```

Ollama will run in the background on `http://localhost:11434`.

### Linux

```bash
# Install using the official install script
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama
ollama serve

# Optional: Run as a system service
sudo systemctl enable ollama
sudo systemctl start ollama
```

### Windows

1. Download the installer from [ollama.ai](https://ollama.ai)
2. Run the installer (`.exe` file)
3. Ollama will start automatically in your system tray
4. Verify it's running by opening `http://localhost:11434` in your browser

### Verify Installation

```bash
# Check Ollama is running
ollama list

# You should see a list of installed models (may be empty initially)
```

If you see connection errors, make sure Ollama is running:

```bash
# macOS/Linux: Start the service
ollama serve

# Windows: Ollama should auto-start, check system tray
```

## Pulling a Model

Ollama needs a model to generate responses. SecondBrain defaults to `llama3.2`, a compact model suitable for local use.

```bash
# Pull the default model (llama3.2)
ollama pull llama3.2

# This downloads ~2GB. Progress will be shown.
```

### Alternative Models

You can use other models if preferred:

```bash
# Pull alternative models
ollama pull llama3.1      # More capable, larger (~4GB)
ollama pull mistral       # Good balance (~4GB)
ollama pull phi3          # Small and fast (~2GB)
ollama pull gemma2        # Google's model (~2GB)
```

**Recommendation**: Start with `llama3.2` for speed, switch to `llama3.1` or `mistral` for better quality if you have the resources.

### Verify Model is Ready

```bash
# List available models
ollama list

# You should see llama3.2 (or your chosen model) in the list
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
# 1. Check Ollama is running
secondbrain chat --check-llm
# Output: ✓ Ollama is available (model: llama3.2)

# 2. Start a new conversation session
secondbrain chat --session project-review

# 3. Ask high-level questions
secondbrain chat --session project-review "What is this project?"

# 4. Dive deeper
secondbrain chat --session project-review "How does document ingestion work?"

# 5. Ask follow-ups that reference earlier context
secondbrain chat --session project-review "Can it handle large files?"

# 6. See sources for verification
secondbrain chat --session project-review "What formats are supported?" --show-sources

# 7. Check session status
secondbrain chat --list-sessions

# 8. View the conversation
secondbrain chat --session project-review --history

# 9. When done, delete the session
secondbrain chat --delete-session project-review
```

## Configuration Options

### Environment Variables

Configure RAG behavior in your `.env` file:

```bash
# Ollama settings
SECONDBRAIN_OLLAMA_HOST=http://localhost:11434
SECONDBRAIN_LLM_MODEL=llama3.2
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
| `--model, -m` | `llama3.2` | LLM model name |
| `--show-sources` | `false` | Display retrieved sources |
| `--list-sessions` | `false` | List all sessions |
| `--history` | `false` | Show session history |
| `--delete-session, -d` | - | Delete a session |
| `--check-llm` | `false` | Check Ollama availability |

## Troubleshooting

### Ollama Unreachable

```bash
# Check if Ollama is running
secondbrain chat --check-llm

# If not running, start it
ollama serve

# Verify model is downloaded
ollama list
```

### Model Not Found

```bash
# Pull the model
ollama pull llama3.2

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

# Check Ollama
secondbrain chat --check-llm

# Exit interactive mode
/quit
```

Happy chatting with your documents!
