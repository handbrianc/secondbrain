# Conversational Q&A

Multi-turn question answering over your ingested documents, powered by the
RAG pipeline (`secondbrain.rag.pipeline`). The `chat` command retrieves
relevant chunks, keeps session history in SQLite, rewrites follow-up
questions so pronouns resolve against earlier turns, and streams the answer
to your terminal.

## What it does

For each question the pipeline:

1. Detects the structural intent of the query (printed to stderr).
2. Rewrites follow-up questions into standalone form using recent history
   ("what about page 2?" → "what is on page 2 of <document>?").
3. Retrieves the top-k chunks from the vector store, with a minimum
   similarity threshold (default 0.46).
4. Builds a prompt from the retrieved context plus the last few messages
   (context window default 5) and a configurable system prompt.
5. Generates the answer through the configured LLM provider, streaming it
   token by token; reasoning/thinking tokens stream in gray before the
   answer when the model emits them.
6. Persists the user and assistant messages to the session.

If retrieval finds nothing relevant and `SECONDBRAIN_RAG_LLM_FALLBACK_ENABLED`
is true (default), the assistant says the documents don't cover the topic and
then answers from its general knowledge.

## How to run it

### One-off question

```bash
secondbrain chat "What is secondbrain?"
```

The answer streams to the terminal. Nothing is kept open afterwards.

### Interactive mode

Run `chat` without a query:

```bash
secondbrain chat --session my-chat
```

This opens a REPL (`[you]` prompt). Built-in commands:

| Command | Effect |
| ------- | ------ |
| `/quit`, `/exit` | Leave the chat |
| `/clear` | Clear the session's conversation history |
| `/help` | List the commands |

Your input history (up to 1000 lines) is persisted with readline to
`~/.secondbrain_chat_history` for arrow-key recall across runs.

### Sessions

Session state lives in SQLite (see below). Useful operations:

```bash
# Continue a named session (created on first use if it doesn't exist yet)
secondbrain chat --session my-chat

# Create a fresh auto-generated UUID session, even if --session is also given
secondbrain chat --create

# Show the last 20 messages of a session
secondbrain chat --session my-chat --history

# List sessions with message counts and creation times
secondbrain chat --list-sessions

# Delete a session (asks for confirmation)
secondbrain chat --delete-session my-chat
```

If you pass `--session` with a name that doesn't exist yet, a new session is
created with that name — resuming and creating are the same operation.
Without `--session` or `--create`, single-turn and interactive chats run in a
session named `default`.

### Health check

```bash
secondbrain chat --check-llm
```

Verifies the configured LLM provider is reachable and reports
`✓ LLM provider (<provider>) is healthy` or an error message. Run this
before a long session to catch missing API keys or a bad endpoint.

## Command options

| Option | Default | Description |
| ------ | ------- | ----------- |
| `QUERY` (argument) | — | Question to ask; omit for interactive mode |
| `--session`, `-s` | `default` | Session ID to use/create |
| `--create`, `-c` | off | Create a new UUID session (overrides `--session`) |
| `--top-k`, `-k` | `20` | Chunks retrieved per question |
| `--temperature`, `-t` | `0.1` | Accepted for compatibility; currently not applied (see [Limitations](#limitations)) |
| `--model`, `-m` | — | Accepted for compatibility; currently not applied (see [Limitations](#limitations)) |
| `--show-sources` | off | Print the retrieved chunks (file, page, 200-char preview) after each answer |
| `--list-sessions` | off | List stored sessions and exit |
| `--history` | off | Show the last 20 messages of `--session` and exit |
| `--delete-session`, `-d` | — | Delete the named session (with confirmation) and exit |
| `--check-llm` | off | Test provider connectivity and exit |

## Configuration reference

All settings are `SECONDBRAIN_*` environment variables (set them directly or
in a `.env` file). The CLI also accepts `--verbose/-v` globally.

### LLM provider

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `SECONDBRAIN_LLM_PROVIDER` | `openai` | `openai` or `anthropic` (anything else raises an error) |
| `SECONDBRAIN_LLM_MODEL` | `gpt-4o-mini` | Model passed to the provider (e.g. `claude-3-sonnet-20240229` for Anthropic) |
| `SECONDBRAIN_LLM_TEMPERATURE` | `0.3` | Generation temperature (0.0–2.0) |
| `SECONDBRAIN_LLM_TOP_P` | `0.95` | Nucleus-sampling top_p (0.0–1.0) |
| `SECONDBRAIN_LLM_MAX_TOKENS` | `384000` | Maximum tokens for responses |
| `SECONDBRAIN_LLM_MAX_ANSWER_CHARS` | `24000` | Upper bound on streamed answer length; `0` disables |
| `SECONDBRAIN_LLM_TIMEOUT` | `120` | Request timeout in seconds |
| `SECONDBRAIN_LLM_STREAM_IDLE_TIMEOUT_SECONDS` | `600` | Abort if no streamed token arrives for this long; `0` disables |
| `SECONDBRAIN_LLM_REPETITION_PENALTY` | `1.0` | ≥ 1.0; sent to OpenAI-compatible servers that support it |
| `SECONDBRAIN_LLM_REASONING_EFFORT` | unset | `minimal`/`low`/`medium`/`high` hint for reasoning models |

Provider credentials and endpoints:

| Variable | Description |
| -------- | ----------- |
| `SECONDBRAIN_OPENAI_API_KEY` | Required for the `openai` provider (unless the endpoint needs no auth) |
| `SECONDBRAIN_OPENAI_BASE_URL` | Optional OpenAI-compatible base URL for self-hosted endpoints (vLLM, LM Studio, Azure OpenAI, Groq, …) |
| `SECONDBRAIN_ANTHROPIC_API_KEY` | Required for the `anthropic` provider |

The `anthropic` provider defaults to `claude-3-sonnet-20240229` when
`SECONDBRAIN_LLM_MODEL` is not set. Only `openai` and `anthropic` are
supported; `SECONDBRAIN_LLM_PROVIDER=ollama` (or any other value) fails with
`Unsupported LLM provider`.

### Retrieval and RAG behavior

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `SECONDBRAIN_RAG_CONTEXT_WINDOW` | `5` | Recent messages kept in the prompt |
| `SECONDBRAIN_RAG_MAX_RETRIES` | `3` | Retry attempts for LLM generation |
| `SECONDBRAIN_RAG_LLM_FALLBACK_ENABLED` | `true` | Answer from general knowledge when no relevant chunks are found |
| `SECONDBRAIN_RAG_MIN_SIMILARITY_THRESHOLD` | `0.46` | Minimum cosine score for a chunk to count as context |
| `SECONDBRAIN_RAG_SCOPED_MIN_SIMILARITY_THRESHOLD` | `0.20` | Lower threshold applied when the query names a specific document |
| `SECONDBRAIN_RAG_MAX_CONTEXT_CHARS` | `16000` | Total context budget for the prompt |
| `SECONDBRAIN_RAG_CHUNK_PREVIEW_CHARS` | `1200` | Per-chunk text budget in the prompt |
| `SECONDBRAIN_RAG_SYSTEM_PROMPT` | built-in grounding prompt | Replace the whole system prompt |

### Session storage

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `SECONDBRAIN_SQLITE_PATH` | `~/.secondbrain/secondbrain.db` | SQLite database file for conversation sessions |

## Session storage behavior

Sessions are stored in an embedded SQLite database (no server). The file is
created on first use, including parent directories. Two tables hold the
state:

- `sessions` — `session_id`, `created_at`, `updated_at`
- `messages` — one row per message: `session_id`, `position`, `role`
  (`user`/`assistant`), `content`, `timestamp`

Messages keep strict positional order; the context window trims by dropping
everything older than the last `SECONDBRAIN_RAG_CONTEXT_WINDOW` messages.
The connection uses WAL journaling for concurrent readers and serializes
writes behind a lock, so one writer at a time is safe. `--list-sessions`
reports up to 100 sessions with message counts; `--delete-session` removes
the session and cascades to its messages. `/clear` in interactive mode
replaces the stored messages with an empty history.

Note that the database also serves as the general data path for the CLI, so
it may exist even before your first chat if other commands have run.

## Limitations

- `--temperature` and `--model` are accepted but currently have no effect:
  the provider is always built from the `SECONDBRAIN_LLM_*` environment
  settings. Change the model via `SECONDBRAIN_LLM_MODEL` instead.
- Session storage is synchronous SQLite only; there is no async session API.
- The chat path does not forward file-type filters to retrieval (source
  scoping works when your query names an ingested document).
- Token usage is not reported; latency is tracked internally only.
- Answers depend on retrieval quality: chunking choices made at ingestion
  time (chunk size/overlap) affect what the assistant can find.
