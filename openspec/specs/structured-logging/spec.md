## ADDED Requirements

### Requirement: JSON log format support
The logging system SHALL support JSON-formatted log output for production environments.

#### Scenario: JSON format produces valid JSON
- **WHEN** setup_json_logging() is called
- **THEN** each log line SHALL be valid JSON
- **AND** SHALL be parseable by standard JSON parsers

#### Scenario: JSON includes standard fields
- **WHEN** a log record is formatted as JSON
- **THEN** it SHALL include: timestamp, level, logger, message, module, function, line
- **AND** it SHALL include: request_id (if set)

### Requirement: Request ID correlation
The logging system SHALL support request ID tracking via context variables.

#### Scenario: Request ID is auto-generated
- **WHEN** set_request_id() is called without argument
- **THEN** a new UUID SHALL be generated
- **AND** it SHALL be stored in context var

#### Scenario: Request ID is included in logs
- **WHEN** logging occurs after set_request_id()
- **THEN** log output SHALL include the request ID
- **AND** request ID SHALL propagate across async tasks

#### Scenario: Request ID can be manually set
- **WHEN** set_request_id() is called with argument
- **THEN** provided ID SHALL be used
- **AND** it SHALL be used for correlation

### Requirement: Configurable log format
The log format SHALL be configurable via environment variable.

#### Scenario: SECONDBRAIN_LOG_FORMAT=json enables JSON
- **WHEN** SECONDBRAIN_LOG_FORMAT=json is set
- **THEN** logs SHALL be formatted as JSON
- **AND** Rich formatting SHALL be disabled

#### Scenario: SECONDBRAIN_LOG_FORMAT=rich enables rich text
- **WHEN** SECONDBRAIN_LOG_FORMAT=rich is set
- **THEN** logs SHALL use Rich formatting
- **AND** colored output SHALL be enabled

#### Scenario: Default format is rich text
- **WHEN** SECONDBRAIN_LOG_FORMAT is not set
- **THEN** logs SHALL default to Rich formatting
- **AND** console output SHALL be human-readable

### Requirement: Standardized log levels
The logging system SHALL use standard log levels consistently.

#### Scenario: DEBUG level for detailed debugging
- **WHEN** verbose mode is enabled
- **THEN** DEBUG level logs SHALL be shown
- **AND** they SHALL include detailed internal state

#### Scenario: INFO level for normal operations
- **WHEN** normal operations occur
- **THEN** INFO level logs SHALL be shown by default
- **AND** they SHALL include key events (ingestion, search)

#### Scenario: WARNING level for non-critical issues
- **WHEN** non-critical issues occur
- **THEN** WARNING level logs SHALL be shown
- **AND** they SHALL indicate recoverable issues

#### Scenario: ERROR level for failures
- **WHEN** operations fail
- **THEN** ERROR level logs SHALL be shown
- **AND** they SHALL include exception details

### Requirement: Log handler configuration
The logging system SHALL support configurable log handlers.

#### Scenario: Console handler is default
- **WHEN** logging is set up
- **THEN** console handler SHALL be configured
- **AND** logs SHALL output to stderr

#### Scenario: File handler can be added
- **WHEN** SECONDBRAIN_LOG_FILE is set
- **THEN** file handler SHALL be added
- **AND** logs SHALL be written to specified file

#### Scenario: Log rotation is supported
- **WHEN** file logging is enabled
- **THEN** RotatingFileHandler SHALL be used
- **AND** max size SHALL be configurable (default: 10MB)

### Requirement: Integration with CLI
The logging setup SHALL integrate with CLI verbose flag.

#### Scenario: --verbose enables DEBUG level
- **WHEN** user runs with --verbose flag
- **THEN** log level SHALL be set to DEBUG
- **AND** detailed logs SHALL be shown

#### Scenario: --verbose works with JSON format
- **WHEN** --verbose is used with SECONDBRAIN_LOG_FORMAT=json
- **THEN** DEBUG level JSON logs SHALL be output
- **AND** format SHALL remain valid JSON
