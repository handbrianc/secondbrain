## ADDED Requirements

### Requirement: OpenTelemetry SDK integration
The system SHALL integrate OpenTelemetry SDK for distributed tracing.

#### Scenario: Tracer provider is configured
- **WHEN** application starts with tracing enabled
- **THEN** OpenTelemetry tracer provider SHALL be initialized
- **AND** resource attributes SHALL include service name

#### Scenario: Traces are exported
- **WHEN** spans are created
- **THEN** they SHALL be exported to configured endpoint
- **AND** export SHALL be asynchronous (non-blocking)

### Requirement: Ingestion pipeline instrumentation
The ingestion pipeline SHALL be instrumented with OpenTelemetry spans.

#### Scenario: Ingestion creates root span
- **WHEN** ingest() is called
- **THEN** "document.ingest" span SHALL be created
- **AND** it SHALL include file path as attribute

#### Scenario: File processing creates child spans
- **WHEN** individual files are processed
- **THEN** "document.process" span SHALL be created
- **AND** it SHALL be child of ingestion span
- **AND** it SHALL include processing time

#### Scenario: Embedding generation is traced
- **WHEN** embeddings are generated
- **THEN** "embedding.generate" span SHALL be created
- **AND** it SHALL include text length attribute
- **AND** it SHALL include embedding dimensions

#### Scenario: Storage operations are traced
- **WHEN** documents are stored
- **THEN** "storage.store" span SHALL be created
- **AND** it SHALL include document count attribute
- **AND** it SHALL include storage duration

### Requirement: Search query instrumentation
Search operations SHALL be instrumented with OpenTelemetry spans.

#### Scenario: Search creates root span
- **WHEN** search() is called
- **THEN** "search.query" span SHALL be created
- **AND** it SHALL include query length attribute

#### Scenario: Embedding search is traced
- **WHEN** vector search is performed
- **THEN** "search.vector" span SHALL be created
- **AND** it SHALL include top_k attribute
- **AND** it SHALL include result count

### Requirement: MongoDB operation instrumentation
MongoDB operations SHALL be automatically instrumented.

#### Scenario: Database queries are traced
- **WHEN** MongoDB operations occur
- **THEN** "db.mongodb.query" span SHALL be created
- **AND** it SHALL include collection name
- **AND** it SHALL include operation type

#### Scenario: Query performance is measured
- **WHEN** MongoDB queries execute
- **THEN** span duration SHALL reflect query time
- **AND** slow queries SHALL be identifiable

### Requirement: Error tracing
Errors SHALL be captured in OpenTelemetry spans.

#### Scenario: Exceptions are recorded as span events
- **WHEN** an exception occurs
- **THEN** "exception" event SHALL be added to span
- **AND** exception type SHALL be recorded
- **AND** exception message SHALL be recorded

#### Scenario: Failed spans are marked
- **WHEN** span execution fails
- **THEN** span status SHALL be set to ERROR
- **AND** error description SHALL be included

### Requirement: Metrics collection
The system SHALL collect and export OpenTelemetry metrics.

#### Scenario: Request count metric exists
- **WHEN** operations complete
- **THEN** "secondbrain.operations.count" metric SHALL be incremented
- **AND** it SHALL include operation type label

#### Scenario: Duration metrics exist
- **WHEN** operations complete
- **THEN** "secondbrain.operations.duration" histogram SHALL be recorded
- **AND** it SHALL include operation type label

#### Scenario: Error rate metric exists
- **WHEN** errors occur
- **THEN** "secondbrain.errors.count" metric SHALL be incremented
- **AND** it SHALL include error type label

### Requirement: Configurable tracing
OpenTelemetry tracing SHALL be configurable via environment variables.

#### Scenario: Tracing can be enabled/disabled
- **WHEN** SECONDBRAIN_TRACING_ENABLED=false
- **THEN** tracing SHALL be disabled
- **AND** no overhead SHALL be incurred

#### Scenario: Export endpoint is configurable
- **WHEN** SECONDBRAIN_OTEL_EXPORTER_ENDPOINT is set
- **THEN** traces SHALL be exported to that endpoint
- **AND** default SHALL be OTLP localhost:4317

#### Scenario: Sampling rate is configurable
- **WHEN** SECONDBRAIN_OTEL_SAMPLING_RATE is set
- **THEN** that sampling rate SHALL be used
- **AND** default SHALL be 1.0 (100%)

### Requirement: Propagation of trace context
Trace context SHALL propagate across service boundaries.

#### Scenario: HTTP requests carry trace context
- **WHEN** HTTP requests are made
- **THEN** W3C trace context headers SHALL be added
- **AND** downstream services SHALL receive trace ID

#### Scenario: Async tasks propagate context
- **WHEN** async tasks are spawned
- **THEN** trace context SHALL be propagated
- **AND** child spans SHALL link to parent trace
