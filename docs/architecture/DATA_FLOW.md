# Data Flow

Detailed processing pipelines for SecondBrain operations.

## Document Ingestion Flow

### High-Level Pipeline

```
File → Discovery → Parsing → Text Extraction → Chunking → Embedding → Storage
```

### Stage Breakdown

#### 1. File Discovery

Given a path (file or directory):

```
Input Path
    │
    ├─► If file: process immediately
    │
    └─► If directory:
         │
         ├─► --recursive: rglob(**) finds all nested files
         │
         └─► No recursion: glob(*) finds immediate children
              │
              └─► Filter: is_file() AND supported_extension
```

#### 2. Document Parsing (Docling)

Multiple parsers handle different formats:

| Format | Parser Action |
|--------|---------------|
| PDF | PdfParser extracts text, tables, structure |
| DOCX | DocxParser reads paragraphs, tables |
| HTML | HtmlParser strips tags, preserves text |
| Images | DocLing OCR extracts text via Vision |
| Audio | Audio transcription (future) |

Output: Raw text string with page/position metadata

#### 3. Text Chunking

Split text into overlapping chunks:

```
Raw Text
    │
    └─► Character-level sliding window
         │
         ├─► Window size: CHUNK_SIZE (default 4096)
         │
         ├─► Step size: CHUNK_SIZE - CHUNK_OVERLAP
         │
         └─► Stop at natural boundaries (paragraph, sentence)
```

Result: List of `{text, chunk_index, start_pos, end_pos}`

#### 4. Embedding Generation

Convert chunks to vectors:

```
Chunks[]
    │
    └─► Batch API call to embedding provider
         │
         ├─► HTTP POST to EMBEDDING_API_BASE
         │
         ├─► Payload: {"input": ["chunk1", "chunk2", ...]}
         │
         └─► Response: [[0.123, -0.456, ...], [...]]

Vectors[] (parallel)
```

#### 5. MongoDB Storage

Persist chunk and vector:

```
MongoDB.insert({
    chunk_id: uuid4(),
    chunk_index: i,
    text: chunk_text,
    text_compressed: gzip(text) if enabled,
    vector: embedding_array,
    vector_dtype: "float32",
    metadata: {
        source: original_file_path,
        page: page_number,
        file_type: extension,
        created_at: datetime.utcnow(),
        size: original_file_size
    }
})
    │
    └─► Create/update vector search index
```

## Search Flow

### High-Level Pipeline

```
Query Text → Embedding → Vector Search → Results Ranking → Display
```

### Stage Breakdown

#### 1. Query Embedding

```
User Query String
    │
    └─► Single embedding API call
         │
         ├─► Same model as ingestion
         │
         └─► Returns fixed-dimension vector
```

#### 2. Vector Search (MongoDB $vectorSearch)

```
Embedded Query Vector
    │
    └─► MongoDB Query:
         {
           $vectorSearch: {
             index: "vector_index",
             path: "vector",
             queryVector: query_vector,
             numCandidates: 100,
             limit: TOP_K
           }
         }

Result: Matching documents ordered by score
```

#### 3. Optional Filtering

Post-search refinement applies metadata filters:

```
Search Results
    │
    └─► If --source filter:
         │
         └─► Keep only where metadata.source matches

         If --file-type filter:
         │
         └─► Keep only where metadata.file_type matches

         If --min-score threshold:
         │
         └─► Keep only where score >= threshold
```

#### 4. Result Display

Format and present results:

```
Filtered Matches
    │
    ├─► TABLE format: Rich console table with columns
    │       [score, source, page, text_preview]
    │
    └─► JSON format: Structured objects per match
```

## Chat (RAG) Flow

### High-Level Pipeline

```
User Query → Retrieve → Augment Prompt → LLM Generate → Present
```

### Stage Breakdown

#### 1. Retrieval

Identical to search flow:

```
Query String
    │
    └─► Same embedding + $vectorSearch pipeline
         │
         └─► Retrieves TOP_K chunks (default 20)
```

#### 2. Context Assembly

Build prompt with retrieved context:

```
RAG System Prompt (SECONDBRAIN_RAG_SYSTEM_PROMPT)
    │
    └─► Insert chunks with format:
         │
         ├─► Source attribution header
         │
         ├─► Per-chunk: "Chunk N from [SOURCE] (page P): [TEXT]"
         │
         └─► Respect RAG_MAX_CONTEXT_CHARS limit

Combined: System Prompt + Context Blocks + User Query
```

#### 3. LLM Generation

Send augmented prompt to LLM:

```
Assembled Prompt
    │
    └─► HTTP to LLM Provider (OpenAI/Anthropic/etc.)
         │
         ├─► Model: LLM_MODEL (default gpt-4o-mini)
         │
         ├─► Temperature: LLM_TEMPERATURE (default 0.1)
         │
         └─► Max tokens: LLM_MAX_TOKENS (default 2048)
```

#### 4. Session Tracking

Conversation context persisted:

```
Interaction stored in MongoDB sessions collection:
{
    session_id: "user-specified or uuid",
    messages: [
        {role: "user", content: "...", timestamp: ...},
        {role: "assistant", content: "...", timestamp: ...}
    ],
    created_at: ...,
    updated_at: ...
}
```

Context window limited to RAG_CONTEXT_WINDOW messages.

## Async Flow Variations

Sync operations use straightforward linear execution. Async variants interleave operations:

### Parallel Embedding

```
Batch of N chunks
    │
    └─►asyncio.gather(*[
          embed_single(chunk) for chunk in chunks
        ])
         │
         └─► N concurrent HTTP requests (rate-limited)
```

### Stream Processing

Memory-efficient ingestion of large files:

```
Large Document
    │
    └─► Yield chunks in stream
         │
         ├─► Parse page by page
         │
         ├─► Chunk each page
         │
         └─► Yield completed chunks immediately
              │
              └─► Downstream embed/store receives chunks
                   as they're ready
```