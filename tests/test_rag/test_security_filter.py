"""Tests for SecurityFilter."""


from secondbrain.rag.security_filter import SecurityFilter, SecurityViolation


class TestSecurityFilterInit:
    """Test SecurityFilter initialization."""

    def test_init_compiles_patterns(self):
        """Test that init compiles all regex patterns."""
        filter_obj = SecurityFilter()

        assert len(filter_obj._sql_patterns) > 0
        assert len(filter_obj._xss_patterns) > 0
        assert len(filter_obj._cmd_patterns) > 0
        assert len(filter_obj._proto_patterns) > 0


class TestSecurityFilterValidateQuery:
    """Test SecurityFilter.validate_query method."""

    def test_validate_safe_query(self):
        """Test that safe queries return empty list."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("What is machine learning?")

        assert violations == []

    def test_detects_sql_injection_select(self):
        """Test detection of SQL SELECT injection."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("SELECT * FROM users")

        assert len(violations) > 0
        assert violations[0].violation_type == "sql_injection"

    def test_detects_sql_injection_drop_table(self):
        """Test detection of DROP TABLE injection."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("DROP TABLE users")

        assert len(violations) > 0
        assert violations[0].violation_type == "sql_injection"

    def test_detects_sql_injection_comment(self):
        """Test detection of SQL comment injection."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("admin' --")

        assert len(violations) > 0
        assert violations[0].violation_type == "sql_injection"

    def test_detects_xss_script_tag(self):
        """Test detection of XSS script injection."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("<script>alert('xss')</script>")

        assert len(violations) > 0
        assert violations[0].violation_type == "xss_injection"

    def test_detects_xss_javascript_protocol(self):
        """Test detection of javascript: protocol."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("javascript:alert('xss')")

        assert len(violations) > 0
        assert violations[0].violation_type == "xss_injection"

    def test_detects_command_injection_rm(self):
        """Test detection of command injection with rm."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("; rm -rf /")

        assert len(violations) > 0
        assert violations[0].violation_type == "command_injection"

    def test_detects_command_injection_cat(self):
        """Test detection of command injection with cat."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("; cat /etc/passwd")

        assert len(violations) > 0
        assert violations[0].violation_type == "command_injection"

    def test_detects_command_injection_backtick(self):
        """Test detection of command injection with backticks."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("test `whoami`")

        assert len(violations) > 0
        assert violations[0].violation_type == "command_injection"

    def test_detects_command_injection_dollar_paren(self):
        """Test detection of command injection with $()."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("test $(whoami)")

        assert len(violations) > 0
        assert violations[0].violation_type == "command_injection"

    def test_detects_proto_pollution(self):
        """Test detection of prototype pollution."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("__proto__")

        assert len(violations) > 0
        assert violations[0].violation_type == "prototype_pollution"

    def test_detects_multiple_violations(self):
        """Test detection of multiple violation types."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query(
            "SELECT * FROM users; <script>alert('xss')</script>"
        )

        assert len(violations) >= 2
        violation_types = {v.violation_type for v in violations}
        assert "sql_injection" in violation_types
        assert "xss_injection" in violation_types

    def test_safe_query_with_special_chars(self):
        """Test that safe queries with special chars pass."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("What's the price of $100?")

        assert violations == []

    def test_case_insensitive_sql_detection(self):
        """Test that SQL injection is detected case-insensitively."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("select * from users")

        assert len(violations) > 0
        assert violations[0].violation_type == "sql_injection"

    def test_empty_query(self):
        """Test validation of empty query."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("")

        assert violations == []

    def test_whitespace_only_query(self):
        """Test validation of whitespace-only query."""
        filter_obj = SecurityFilter()

        violations = filter_obj.validate_query("   ")

        assert violations == []


class TestSecurityFilterIsSafe:
    """Test SecurityFilter.is_safe method."""

    def test_is_safe_true_for_safe_query(self):
        """Test is_safe returns True for safe query."""
        filter_obj = SecurityFilter()

        is_safe = filter_obj.is_safe("What is Python?")

        assert is_safe is True

    def test_is_safe_false_for_injection(self):
        """Test is_safe returns False for injection attempt."""
        filter_obj = SecurityFilter()

        is_safe = filter_obj.is_safe("DROP TABLE users")

        assert is_safe is False


class TestSecurityFilterGetSafeResponse:
    """Test SecurityFilter.get_safe_response method."""

    def test_get_safe_response_returns_message(self):
        """Test that get_safe_response returns a message."""
        filter_obj = SecurityFilter()

        response = filter_obj.get_safe_response()

        assert isinstance(response, str)
        assert len(response) > 0


class TestSecurityViolation:
    """Test SecurityViolation dataclass."""

    def test_violation_creation(self):
        """Test creating a SecurityViolation."""
        violation = SecurityViolation(
            violation_type="sql_injection",
            pattern_matched="SELECT * FROM",
            severity="critical"
        )

        assert violation.violation_type == "sql_injection"
        assert violation.pattern_matched == "SELECT * FROM"
        assert violation.severity == "critical"

    def test_violation_default_severity(self):
        """Test that violation has default severity."""
        violation = SecurityViolation(
            violation_type="xss_injection",
            pattern_matched="<script>"
        )

        assert violation.severity == "high"


class TestSecurityFilterPatternCoverage:
    """Test that all pattern categories are covered."""

    def test_sql_patterns_defined(self):
        """Test that SQL injection patterns are defined."""
        assert len(SecurityFilter.SQL_INJECTION_PATTERNS) > 0

    def test_xss_patterns_defined(self):
        """Test that XSS injection patterns are defined."""
        assert len(SecurityFilter.XSS_INJECTION_PATTERNS) > 0

    def test_command_patterns_defined(self):
        """Test that command injection patterns are defined."""
        assert len(SecurityFilter.COMMAND_INJECTION_PATTERNS) > 0

    def test_proto_patterns_defined(self):
        """Test that prototype pollution patterns are defined."""
        assert len(SecurityFilter.PROTOTYPE_POLLUTION_PATTERNS) > 0

    def test_sql_patterns_list(self):
        """Test specific SQL patterns."""
        filter_obj = SecurityFilter()

        test_cases = [
            "SELECT * FROM table",
            "DROP TABLE users",
            "DELETE FROM data",
            "1=1",
        ]

        for query in test_cases:
            violations = filter_obj.validate_query(query)
            assert len(violations) > 0, f"Should detect SQL in: {query}"

    def test_xss_patterns_list(self):
        """Test specific XSS patterns."""
        filter_obj = SecurityFilter()

        test_cases = [
            "<script>alert('xss')</script>",
            "</script>",
            "javascript:void(0)",
        ]

        for query in test_cases:
            violations = filter_obj.validate_query(query)
            assert len(violations) > 0, f"Should detect XSS in: {query}"

    def test_command_patterns_list(self):
        """Test specific command injection patterns."""
        filter_obj = SecurityFilter()

        test_cases = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "`whoami`",
            "$(id)",
        ]

        for query in test_cases:
            violations = filter_obj.validate_query(query)
            assert len(violations) > 0, f"Should detect cmd in: {query}"

    def test_proto_patterns_list(self):
        """Test specific prototype pollution patterns."""
        filter_obj = SecurityFilter()

        test_cases = [
            "__proto__",
            "{{template}}",
        ]

        for query in test_cases:
            violations = filter_obj.validate_query(query)
            assert len(violations) > 0, f"Should detect proto in: {query}"
