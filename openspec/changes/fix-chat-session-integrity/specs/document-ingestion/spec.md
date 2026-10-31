# Document Ingestion (delta)

## ADDED Requirements

### Requirement: Audio ingest stage observability

Audio ingestion SHALL log the duration and outcome of each pipeline stage
(decode, ASR transcription, topic segmentation, chunking, embedding) when
the stage completes, at INFO on success and at WARNING when a stage exceeds
a configured slow-stage threshold or retried. Stage logs SHALL identify the
ingested file (via the request/log context) so a long or stalled ingest is
attributable after the fact. A stage failure SHALL log the failing stage,
elapsed time, and error before the ingest error surfaces.

#### Scenario: Stages leave a timing trail

- **WHEN** an audio file is ingested
- **THEN** each completed stage logs its elapsed time at INFO with the file
  identified
- **AND** a post-ingest reader can tell from the log alone how long
  transcription (vs segmentation vs embedding) took

#### Scenario: Slow stage warns at WARNING level

- **WHEN** a stage's elapsed time exceeds the configured slow-stage threshold
- **THEN** a WARNING names the stage, the file, and the elapsed time
- **AND** no debug-level flag or environment variable is required to see it

### Requirement: Transcription worker wait bound

The wait for an audio transcription worker's result SHALL be bounded
coherently with the stage's expected worst-case work (model initialization
plus transcription time for the audio's duration and batch/window count),
not by a small constant sized for text extraction. A wait that expires SHALL
log the stage, the bound, and the elapsed time at WARNING before the timeout
error surfaces, and the bound SHALL be configurable. Ingest SHALL NOT report
a worker timeout while the worker is still within the derived bound.

#### Scenario: Bound covers model initialization plus short clip

- **WHEN** a short clip's transcription requires a model build that pushes
  total stage time past a text-extraction-sized constant bound (observed:
  408 s successful transcription vs a 300 s `future.result` bound)
- **THEN** the derived bound covers the stage and no spurious worker timeout
  is reported
- **AND** the completed result is consumed normally

#### Scenario: Genuine timeout is attributable

- **WHEN** the transcription stage truly exceeds the derived configurable
  bound
- **THEN** the surfaced error names the transcription stage, the bound, and
  the elapsed time
- **AND** the WARNING trail shows the stage was live before expiry
