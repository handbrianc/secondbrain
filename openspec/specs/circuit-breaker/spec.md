## ADDED Requirements

### Requirement: Circuit breaker state machine
The circuit breaker SHALL implement a state machine with three states: CLOSED (normal operation), OPEN (failing fast), and HALF_OPEN (testing recovery).

#### Scenario: Initial state is CLOSED
- **WHEN** circuit breaker is created
- **THEN** state SHALL be CLOSED

#### Scenario: Transition to OPEN on failure threshold
- **WHEN** failure count reaches threshold (default: 5)
- **THEN** state SHALL transition to OPEN
- **AND** subsequent calls SHALL fail immediately without execution

#### Scenario: Transition to HALF_OPEN after timeout
- **WHEN** OPEN state duration exceeds recovery timeout (default: 30s)
- **THEN** state SHALL transition to HALF_OPEN

#### Scenario: Transition back to CLOSED on success
- **WHEN** HALF_OPEN state and call succeeds
- **THEN** state SHALL transition to CLOSED
- **AND** failure count SHALL reset to zero

#### Scenario: Return to OPEN on failure in HALF_OPEN
- **WHEN** HALF_OPEN state and call fails
- **THEN** state SHALL transition back to OPEN
- **AND** recovery timeout SHALL reset

### Requirement: Failure tracking and threshold
The circuit breaker SHALL track consecutive failures and open when threshold is exceeded.

#### Scenario: Failure count increments on error
- **WHEN** wrapped function raises exception
- **THEN** failure count SHALL increment
- **AND** if count reaches threshold, circuit SHALL open

#### Scenario: Failure count resets on success
- **WHEN** wrapped function executes successfully
- **THEN** failure count SHALL reset to zero

#### Scenario: Failure count is configurable
- **WHEN** circuit breaker is initialized with custom threshold
- **THEN** threshold SHALL be used instead of default (5)

### Requirement: Recovery timeout configuration
The circuit breaker SHALL support configurable recovery timeout with exponential backoff option.

#### Scenario: Default timeout is 30 seconds
- **WHEN** circuit breaker is created without timeout parameter
- **THEN** recovery timeout SHALL be 30 seconds

#### Scenario: Custom timeout is respected
- **WHEN** circuit breaker is initialized with custom timeout
- **THEN** timeout SHALL be used for OPEN → HALF_OPEN transition

#### Scenario: Exponential backoff doubles timeout
- **WHEN** circuit breaker re-opens after failed HALF_OPEN test
- **THEN** timeout SHALL double (up to maximum of 5 minutes)

### Requirement: Integration with ValidatableService
The circuit breaker SHALL integrate with ValidatableService to protect service validation calls.

#### Scenario: Validation calls are wrapped
- **WHEN** ValidatableService.validate_connection() is called
- **THEN** call SHALL go through circuit breaker
- **AND** failures SHALL be tracked

#### Scenario: Service recovery clears circuit
- **WHEN** service becomes available after being down
- **WHEN** on_service_recovery() is called
- **THEN** circuit breaker state SHALL reset to CLOSED

### Requirement: Circuit breaker metrics and observability
The circuit breaker SHALL expose metrics for monitoring and observability.

#### Scenario: State changes are logged
- **WHEN** circuit transitions between states
- **THEN** log entry SHALL be created with timestamp and reason

#### Scenario: Failure count is queryable
- **WHEN** get_failure_count() is called
- **THEN** current failure count SHALL be returned

#### Scenario: State is queryable
- **WHEN** get_state() is called
- **THEN** current state (CLOSED/OPEN/HALF_OPEN) SHALL be returned

### Requirement: Thread-safe operation
The circuit breaker SHALL be thread-safe for concurrent access.

#### Scenario: Concurrent calls don't corrupt state
- **WHEN** multiple threads call wrapped function simultaneously
- **THEN** state transitions SHALL be atomic
- **AND** no race conditions SHALL occur

#### Scenario: Concurrent failures are counted correctly
- **WHEN** multiple threads experience failures
- **THEN** failure count SHALL accurately reflect total failures
