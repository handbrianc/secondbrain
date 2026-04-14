"""Security filtering for RAG pipeline input validation.

This module provides injection attack detection and prevention
for the SecondBrain RAG system.
"""

import re
from dataclasses import dataclass
from typing import Pattern


@dataclass(frozen=True)
class SecurityViolation:
    """Represents a detected security violation.

    Attributes:
        violation_type: Type of injection detected (sql, xss, cmd, prototype).
        pattern_matched: The pattern that triggered the violation.
        severity: Severity level (high, critical).
    """

    violation_type: str
    pattern_matched: str
    severity: str = "high"


class SecurityFilter:
    """Detects and prevents injection attacks in user queries.

    This filter validates incoming queries against known injection patterns
    and rejects potentially malicious input before it reaches the RAG pipeline.

    Attributes:
        patterns: Compiled regex patterns for injection detection.
    """

    SQL_INJECTION_PATTERNS: list[str] = [
        r"(?i)\bSELECT\s+\*\s+FROM\b",
        r"(?i)\bDROP\s+TABLE\b",
        r"(?i)\bDELETE\s+FROM\b",
        r"(?i)\bINSERT\s+INTO\b",
        r"(?i)\bUPDATE\s+\w+\s+SET\b",
        r"--",
        r"';",
        r"(?i)\b1\s*=\s*1\b",
    ]

    XSS_INJECTION_PATTERNS: list[str] = [
        r"<\s*script",
        r"</\s*script\s*>",
        r"javascript\s*:",
        r"\bon(error|load|click)\s*=",
        r"<\s*iframe",
        r"<\s*img\s+[^>]*onerror",
    ]

    COMMAND_INJECTION_PATTERNS: list[str] = [
        r";\s*rm\s+",
        r"\|\s*rm\s+",
        r"&&\s*rm\s+",
        r";\s*cat\s+",
        r"\|\s*cat\s+",
        r";\s*ls\s+",
        r"`[^`]+`",
        r"\$\([^)]+\)",
    ]

    PROTOTYPE_POLLUTION_PATTERNS: list[str] = [
        r"__proto__",
        r"constructor\s*\.\s*constructor",
        r"\{\{",
        r"\}\}",
        r"Object\.defineProperty",
    ]

    def __init__(self) -> None:
        """Initialize security filter with compiled patterns."""
        self._sql_patterns: list[Pattern[str]] = [
            re.compile(p) for p in self.SQL_INJECTION_PATTERNS
        ]
        self._xss_patterns: list[Pattern[str]] = [
            re.compile(p) for p in self.XSS_INJECTION_PATTERNS
        ]
        self._cmd_patterns: list[Pattern[str]] = [
            re.compile(p) for p in self.COMMAND_INJECTION_PATTERNS
        ]
        self._proto_patterns: list[Pattern[str]] = [
            re.compile(p) for p in self.PROTOTYPE_POLLUTION_PATTERNS
        ]

    def validate_query(self, query: str) -> list[SecurityViolation]:
        """Validate a query for injection attempts.

        Args:
            query: User query string to validate.

        Returns:
            List of SecurityViolation objects for detected patterns.
            Empty list if query is safe.
        """
        violations: list[SecurityViolation] = []

        for pattern in self._sql_patterns:
            if pattern.search(query):
                violations.append(
                    SecurityViolation(
                        violation_type="sql_injection",
                        pattern_matched=pattern.pattern,
                        severity="critical",
                    )
                )

        for pattern in self._xss_patterns:
            if pattern.search(query):
                violations.append(
                    SecurityViolation(
                        violation_type="xss_injection",
                        pattern_matched=pattern.pattern,
                        severity="high",
                    )
                )

        for pattern in self._cmd_patterns:
            if pattern.search(query):
                violations.append(
                    SecurityViolation(
                        violation_type="command_injection",
                        pattern_matched=pattern.pattern,
                        severity="critical",
                    )
                )

        for pattern in self._proto_patterns:
            if pattern.search(query):
                violations.append(
                    SecurityViolation(
                        violation_type="prototype_pollution",
                        pattern_matched=pattern.pattern,
                        severity="high",
                    )
                )

        return violations

    def is_safe(self, query: str) -> bool:
        """Check if a query is safe to process.

        Args:
            query: User query string to validate.

        Returns:
            True if query passes all security checks, False otherwise.
        """
        return len(self.validate_query(query)) == 0

    def get_safe_response(self) -> str:
        """Get the safe refusal message for blocked queries.

        Returns:
            Standardized error message for security violations.
        """
        return (
            "I cannot process queries containing potentially malicious code. "
            "Please rephrase your question without code snippets, commands, "
            "or special syntax."
        )
