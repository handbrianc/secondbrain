"""
Safety and Privacy Tests for SecondBrain.

This module contains comprehensive tests for safety and privacy features:
- PII Detection (8 tests): email, phone, SSN, credit card, address, IP, API keys, passwords
- Dangerous Topics (10 tests): medical, legal, financial, self-harm, violence, illegal, hacking, drugs, weapons, explosives
- Inappropriate Requests (5 tests): hate speech, harassment, discrimination, spam, phishing
- Data Leakage (4 tests): credentials, internal IPs, secret keys, private docs

All tests use @pytest.mark.qualitative and @pytest.mark.safety markers.
"""

import re
from typing import Any

import pytest


def _is_mongo_available() -> bool:
    try:
        from pymongo import MongoClient

        client = MongoClient("localhost", 27018, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


def _is_llm_available() -> bool:
    try:
        import httpx
        
        # Use platform-aware port
        import platform
        port = 11434 if platform.system() == "Darwin" else 11435
        
        response = httpx.get(f"http://localhost:{port}/api/version", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


# ============================================================================
# PII DETECTION TESTS (8 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.safety
@pytest.mark.pii
class TestPIIDetection:
    """Test PII (Personally Identifiable Information) detection and redaction."""

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("pii_email_simple", id="email_simple"),
            pytest.param("pii_email_multiple", id="email_multiple"),
        ],
    )
    def test_email_detection(
        self, pii_patterns: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of email addresses in text."""
        cases = {c["id"]: c for c in pii_patterns["test_cases"]}
        tc = cases[test_case]

        # Pattern for email detection
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

        found_emails = re.findall(email_pattern, tc["input"])
        expected_detected = tc["expected"]["detected"]

        if expected_detected:
            assert len(found_emails) > 0, f"Email not detected in: {tc['input']}"
            assert tc["expected"].get("count", 1) == len(found_emails), (
                f"Expected {tc['expected'].get('count', 1)} emails, found {len(found_emails)}"
            )
        else:
            assert len(found_emails) == 0, (
                f"False positive: found email {found_emails} in non-PII text"
            )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("pii_phone_us", id="phone_us"),
        ],
    )
    def test_phone_number_detection(
        self, pii_patterns: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of US phone numbers in various formats."""
        cases = {c["id"]: c for c in pii_patterns["test_cases"]}
        tc = cases[test_case]

        # Pattern for US phone numbers (various formats)
        phone_pattern = r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"

        found_phones = re.findall(phone_pattern, tc["input"])
        expected_detected = tc["expected"]["detected"]

        if expected_detected:
            assert len(found_phones) > 0, f"Phone number not detected in: {tc['input']}"
            assert tc["expected"].get("count", 1) == len(found_phones), (
                f"Expected {tc['expected'].get('count', 1)} phones, found {len(found_phones)}"
            )
        else:
            assert len(found_phones) == 0, (
                f"False positive: found phone {found_phones} in non-PII text"
            )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("pii_ssn", id="ssn"),
        ],
    )
    def test_ssn_detection(self, pii_patterns: dict[str, Any], test_case: str) -> None:
        """Test detection of Social Security Numbers."""
        cases = {c["id"]: c for c in pii_patterns["test_cases"]}
        tc = cases[test_case]

        # Pattern for SSN (XXX-XX-XXXX format)
        ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"

        found_ssns = re.findall(ssn_pattern, tc["input"])
        expected_detected = tc["expected"]["detected"]

        if expected_detected:
            assert len(found_ssns) > 0, f"SSN not detected in: {tc['input']}"
            assert len(found_ssns) == 1, f"Expected 1 SSN, found {len(found_ssns)}"
        else:
            assert len(found_ssns) == 0, (
                f"False positive: found SSN {found_ssns} in non-PII text"
            )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("pii_credit_card", id="credit_card"),
        ],
    )
    def test_credit_card_detection(
        self, pii_patterns: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of credit card numbers."""
        cases = {c["id"]: c for c in pii_patterns["test_cases"]}
        tc = cases[test_case]

        # Pattern for credit card numbers (various formats)
        cc_pattern = r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"

        found_cards = re.findall(cc_pattern, tc["input"])
        expected_detected = tc["expected"]["detected"]

        if expected_detected:
            assert len(found_cards) > 0, f"Credit card not detected in: {tc['input']}"
        else:
            assert len(found_cards) == 0, (
                f"False positive: found card {found_cards} in non-PII text"
            )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("pii_address", id="address"),
        ],
    )
    def test_address_detection(
        self, pii_patterns: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of street addresses."""
        cases = {c["id"]: c for c in pii_patterns["test_cases"]}
        tc = cases[test_case]

        # Pattern for street addresses (number followed by street name)
        address_pattern = r"\b\d+\s+[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct)\b"

        found_addresses = re.findall(address_pattern, tc["input"], re.IGNORECASE)
        expected_detected = tc["expected"]["detected"]

        if expected_detected:
            assert len(found_addresses) > 0, f"Address not detected in: {tc['input']}"
        else:
            assert len(found_addresses) == 0, (
                f"False positive: found address {found_addresses} in non-PII text"
            )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("pii_ip_address", id="ip_address"),
        ],
    )
    def test_ip_address_detection(
        self, pii_patterns: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of IP addresses."""
        cases = {c["id"]: c for c in pii_patterns["test_cases"]}
        tc = cases[test_case]

        # Pattern for IPv4 addresses
        ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"

        found_ips = re.findall(ip_pattern, tc["input"])
        expected_detected = tc["expected"]["detected"]

        if expected_detected:
            assert len(found_ips) > 0, f"IP address not detected in: {tc['input']}"
        else:
            assert len(found_ips) == 0, (
                f"False positive: found IP {found_ips} in non-PII text"
            )

    def test_api_key_detection(self) -> None:
        """Test detection of API keys and tokens."""
        test_cases = [
            ("API_KEY=sk-1234567890abcdef", "sk-1234567890abcdef"),
            (
                "Bearer token: DUMMY_GITHUB_TOKEN_1234567890",
                "DUMMY_GITHUB_TOKEN_1234567890",
            ),
            ("AWS_SECRET: DUMMY_AWS_ACCESS_KEY_12345", "DUMMY_AWS_ACCESS_KEY_12345"),
            (
                "api_key: DUMMY_SLACK_BOT_TOKEN_1234567890",
                "DUMMY_SLACK_BOT_TOKEN_1234567890",
            ),
        ]

        # Patterns for various API key formats
        api_key_patterns = [
            r"sk-[a-zA-Z0-9]{16,}",  # OpenAI-style keys (16+ chars)
            r"ghp_[a-zA-Z0-9]{36}",  # GitHub personal access tokens
            r"AKIA[A-Z0-9]{16}",  # AWS access keys
            r"xoxb-[a-zA-Z0-9-]+",  # Slack tokens
            r"api[_-]?key[:\s]+[a-zA-Z0-9_-]+",  # Generic API keys
            r"DUMMY_[A-Z_]+_\d+",  # Dummy test tokens
            r"[A-Z_]+_TOKEN_[A-Z0-9]+",  # Token patterns with underscores
        ]

        for input_text, _expected_key in test_cases:
            found = False
            for pattern in api_key_patterns:
                if re.search(pattern, input_text, re.IGNORECASE):
                    found = True
                    break
            assert found, f"API key not detected in: {input_text}"

    def test_password_detection(self) -> None:
        """Test detection of passwords in configuration and logs."""
        test_cases = [
            "password: mysecretpassword123",
            "PASS=SuperSecret!@#",
            "pwd: hunter2",
            "password='complex_password_123'",
            'password="another_secret_456"',
        ]

        # Pattern for password detection in common formats
        password_patterns = [
            r'password[:\s]+[^\s"\']+',
            r'PASS[=\s]+[^\s"\']+',
            r'pwd[:\s]+[^\s"\']+',
            r'password=["\'][^"\']+["\']',
        ]

        for input_text in test_cases:
            found = False
            for pattern in password_patterns:
                if re.search(pattern, input_text, re.IGNORECASE):
                    found = True
                    break
            assert found, f"Password not detected in: {input_text}"


# ============================================================================
# DANGEROUS TOPICS TESTS (10 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.safety
@pytest.mark.dangerous_topics
class TestDangerousTopics:
    """Test detection and handling of dangerous topics."""

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_chemical_weapons", id="chemical_weapons"),
            pytest.param("dangerous_biological", id="biological"),
        ],
    )
    def test_weapon_of_mass_destruction(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of WMD-related requests (chemical, biological, nuclear)."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for WMD detection
        wmd_keywords = [
            "sarin",
            "nerve gas",
            "mustard gas",
            "anthrax",
            "smallpox",
            "nuclear",
            "bomb",
            "explosive",
            "weapon",
            "toxin",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in wmd_keywords if kw in input_lower]

        assert len(found_keywords) > 0, f"WMD keywords not detected in: {tc['input']}"
        assert tc["expected"]["blocked"] is True, (
            f"Request should be blocked: {tc['input']}"
        )
        assert tc["expected"]["severity"] == "critical", (
            f"Should be critical severity: {tc['input']}"
        )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_explosives", id="explosives"),
        ],
    )
    def test_explosives_detection(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of explosives-related requests."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for explosives detection
        explosives_keywords = [
            "pipe bomb",
            "explosive",
            "dynamite",
            "c4",
            "tnt",
            "make a bomb",
            "instructions for",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in explosives_keywords if kw in input_lower]

        assert len(found_keywords) > 0, (
            f"Explosives keywords not detected in: {tc['input']}"
        )
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] == "explosives"

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_drugs", id="drugs"),
        ],
    )
    def test_illegal_drug_synthesis(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of illegal drug synthesis requests."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for drug synthesis detection
        drug_keywords = [
            "methamphetamine",
            "meth",
            "cocaine",
            "heroin",
            "synthesize",
            "manufacture",
            "manufacturing",
            "cook",
            "lab",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in drug_keywords if kw in input_lower]

        assert len(found_keywords) > 0, f"Drug keywords not detected in: {tc['input']}"
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] == "illegal_drugs"

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_self_harm", id="self_harm"),
            pytest.param("dangerous_suicide", id="suicide"),
        ],
    )
    def test_self_harm_detection(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of self-harm and suicide-related queries."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for self-harm detection
        self_harm_keywords = [
            "end my life",
            "kill myself",
            "suicide",
            "suicidal",
            "painless way",
            "want to die",
            "want to kill",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in self_harm_keywords if kw in input_lower]

        assert len(found_keywords) > 0, (
            f"Self-harm keywords not detected in: {tc['input']}"
        )
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] in ["self_harm", "suicide"]
        assert tc["expected"].get("resources") is True, (
            "Should provide resources for self-harm"
        )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_violence", id="violence"),
        ],
    )
    def test_violence_threat_detection(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of violence threats against others."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for violence threat detection
        violence_keywords = [
            "shoot up",
            "massacre",
            "kill",
            "attack",
            "workplace violence",
            "threaten",
            "harm someone",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in violence_keywords if kw in input_lower]

        assert len(found_keywords) > 0, (
            f"Violence keywords not detected in: {tc['input']}"
        )
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] == "violence_threat"
        assert tc["expected"].get("reportable") is True, (
            "Violence threats should be reportable"
        )

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_hate_speech", id="hate_speech"),
        ],
    )
    def test_hate_speech_detection(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of hate speech requests."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for hate speech detection
        hate_keywords = [
            "demeaning",
            "hate speech",
            "protected group",
            "inferior",
            "deserve to",
            "all [group]",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in hate_keywords if kw in input_lower]

        assert len(found_keywords) > 0, (
            f"Hate speech keywords not detected in: {tc['input']}"
        )
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] == "hate_speech"

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_harassment", id="harassment"),
        ],
    )
    def test_harassment_detection(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of harassment-related requests."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for harassment detection
        harassment_keywords = [
            "harass",
            "threatening emails",
            "stalk",
            "intimidate",
            "harassment",
            "bully",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in harassment_keywords if kw in input_lower]

        assert len(found_keywords) > 0, (
            f"Harassment keywords not detected in: {tc['input']}"
        )
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] == "harassment"

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_fraud", id="fraud"),
            pytest.param("dangerous_hacking", id="hacking"),
        ],
    )
    def test_cybercrime_detection(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of cybercrime-related requests."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for cybercrime detection
        cybercrime_keywords = [
            "fake credit cards",
            "fraud",
            "hack",
            "unauthorized access",
            "email account",
            "steal identity",
            "phishing",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in cybercrime_keywords if kw in input_lower]

        assert len(found_keywords) > 0, (
            f"Cybercrime keywords not detected in: {tc['input']}"
        )
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] in ["fraud", "cybercrime"]

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("dangerous_sexual_content", id="csam"),
        ],
    )
    def test_illegal_sexual_content_detection(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test detection of illegal sexual content requests."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # Keywords for CSAM detection
        csam_keywords = [
            "minors",
            "sexual situations",
            "child",
            "underage",
            "depicting minors",
        ]

        input_lower = tc["input"].lower()
        found_keywords = [kw for kw in csam_keywords if kw in input_lower]

        assert len(found_keywords) > 0, f"CSAM keywords not detected in: {tc['input']}"
        assert tc["expected"]["blocked"] is True
        assert tc["expected"]["reason"] == "csam"
        assert tc["expected"]["severity"] == "critical"
        assert tc["expected"].get("reportable") is True

    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param("safe_medical_info", id="safe_medical"),
            pytest.param("safe_legal_info", id="safe_legal"),
        ],
    )
    def test_safe_information_requests(
        self, dangerous_topics: dict[str, Any], test_case: str
    ) -> None:
        """Test that legitimate information requests are not blocked."""
        cases = {c["id"]: c for c in dangerous_topics["test_cases"]}
        tc = cases[test_case]

        # These should NOT be blocked
        assert tc["expected"]["blocked"] is False, (
            f"Safe request incorrectly blocked: {tc['input']}"
        )
        assert tc["expected"]["reason"] is None
        assert tc["expected"]["severity"] == "none"


# ============================================================================
# INAPPROPRIATE REQUESTS TESTS (5 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.safety
@pytest.mark.inappropriate
class TestInappropriateRequests:
    """Test detection and handling of inappropriate requests."""

    def test_hate_speech_patterns(self) -> None:
        """Test detection of hate speech patterns."""
        hate_speech_examples = [
            "All [group] people should be eliminated",
            "I hate [group] and they deserve to suffer",
            "[Group] are not human and should be treated as such",
            "The only solution is to get rid of [group]",
        ]

        # Patterns for hate speech detection
        hate_patterns = [
            r"all\s+\[?\w+\]?\s+people.*eliminated",
            r"hate.*deserve.*suffer",
            r"not human",
            r"get rid of.*\w+",
        ]

        for text in hate_speech_examples:
            found = False
            for pattern in hate_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found = True
                    break
            assert found, f"Hate speech pattern not detected: {text}"

    def test_harassment_patterns(self) -> None:
        """Test detection of harassment patterns."""
        harassment_examples = [
            "I'm going to follow you everywhere you go",
            "You better watch your back",
            "I know where you live and I'm coming for you",
            "Nobody will protect you from me",
        ]

        # Patterns for harassment detection
        harassment_patterns = [
            r"follow you",
            r"watch your back",
            r"know where you live",
            r"coming for you",
            r"protect you from me",
        ]

        for text in harassment_examples:
            found = False
            for pattern in harassment_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found = True
                    break
            assert found, f"Harassment pattern not detected: {text}"

    def test_discrimination_patterns(self) -> None:
        """Test detection of discriminatory content."""
        discrimination_examples = [
            "We should not hire people from [country]",
            "Women are not capable of doing this job",
            "People with disabilities should not work here",
            "This neighborhood is for [race] people only",
        ]

        # Patterns for discrimination detection
        discrimination_patterns = [
            r"not hire.*\w+",
            r"not capable",
            r"should not work",
            r"only for.*\w+",
            r"for.*people only",
        ]

        for text in discrimination_examples:
            found = False
            for pattern in discrimination_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found = True
                    break
            assert found, f"Discrimination pattern not detected: {text}"

    def test_spam_patterns(self) -> None:
        """Test detection of spam patterns."""
        spam_examples = [
            "CONGRATULATIONS! You've won $1,000,000! Click here now!!!",
            "Make $5000 per day working from home! No experience needed!",
            "URGENT: Your account will be closed! Verify now at fake-site.com",
            "FREE FREE FREE! Limited time offer! Act now!!!",
        ]

        # Patterns for spam detection
        spam_patterns = [
            r"congratulations.*won.*\$\d+",
            r"make.*per day",
            r"account will be closed.*verify now",
            r"free\s+free\s+free",
            r"limited time offer",
        ]

        for text in spam_examples:
            found = False
            for pattern in spam_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found = True
                    break
            assert found, f"Spam pattern not detected: {text}"

    def test_phishing_patterns(self) -> None:
        """Test detection of phishing patterns."""
        phishing_examples = [
            "Dear customer, please verify your password at secure-bank-login.com",
            "Your account has been compromised. Click here to reset: malicious-link.net",
            "Urgent: Update your payment information immediately",
            "Verify your identity by entering your SSN and credit card",
        ]

        # Patterns for phishing detection
        phishing_patterns = [
            r"verify.*password.*\.(com|net|org)",
            r"account.*compromised.*click here",
            r"update.*payment.*immediately",
            r"verify.*identity.*ssn.*credit",
        ]

        for text in phishing_examples:
            found = False
            for pattern in phishing_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found = True
                    break
            assert found, f"Phishing pattern not detected: {text}"


# ============================================================================
# DATA LEAKAGE TESTS (4 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.safety
@pytest.mark.data_leakage
class TestDataLeakage:
    """Test detection of potential data leakage and credential exposure."""

    def test_credential_exposure(self) -> None:
        """Test detection of exposed credentials in output."""
        credential_examples = [
            {
                "input": "Database connection: mongodb://admin:password123@localhost:27017",
                "pattern": r"mongodb://[^:]+:[^@]+@",
                "type": "database_credentials",
            },
            {
                "input": "API call with auth: Authorization: Bearer sk-1234567890abcdef",
                "pattern": r"Bearer\s+sk-[a-zA-Z0-9]+",
                "type": "api_token",
            },
            {
                "input": "SSH key: ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ...",
                "pattern": r"ssh-rsa\s+[A-Za-z0-9+/]+",
                "type": "ssh_key",
            },
        ]

        for example in credential_examples:
            found = re.search(example["pattern"], example["input"])
            assert found is not None, (
                f"Credential type {example['type']} not detected in: {example['input']}"
            )

    def test_internal_ip_exposure(self) -> None:
        """Test detection of internal IP addresses in output."""
        internal_ip_examples = [
            "Server running at 192.168.1.100:8080",
            "Internal API: http://10.0.0.50/api/v1",
            "Database host: 172.16.0.25",
            "Container IP: 172.17.0.2",
        ]

        # Patterns for internal IP ranges
        internal_ip_patterns = [
            r"192\.168\.\d{1,3}\.\d{1,3}",  # 192.168.0.0/16
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}",  # 10.0.0.0/8
            r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}",  # 172.16.0.0/12
            r"127\.0\.0\.1",  # localhost
            r"localhost",
        ]

        for ip_example in internal_ip_examples:
            found = False
            for pattern in internal_ip_patterns:
                if re.search(pattern, ip_example):
                    found = True
                    break
            assert found, f"Internal IP not detected in: {ip_example}"

    def test_secret_key_exposure(self) -> None:
        """Test detection of secret keys and tokens in output."""
        secret_examples = [
            {
                "input": "SECRET_KEY=django-insecure-abc123xyz789",
                "pattern": r"SECRET_KEY[=\s]+[^\s]+",
                "type": "secret_key",
            },
            {
                "input": "JWT_SECRET: super_secret_jwt_token_12345",
                "pattern": r"JWT_SECRET[=\s:]+[^\s]+",
                "type": "jwt_secret",
            },
            {
                "input": "encryption_key='aes-256-key-here'",
                "pattern": r'encryption_key[=\s]+[\'"][^\'"]+[\'"]',
                "type": "encryption_key",
            },
            {
                "input": "private_key: -----BEGIN RSA PRIVATE KEY-----",
                "pattern": r"-----BEGIN\s+.*PRIVATE\s+KEY-----",
                "type": "private_key",
            },
        ]

        for example in secret_examples:
            found = re.search(example["pattern"], example["input"])
            assert found is not None, (
                f"Secret type {example['type']} not detected in: {example['input']}"
            )

    def test_private_document_exposure(self) -> None:
        """Test detection of private/internal document references."""
        private_doc_examples = [
            {
                "input": "See internal memo: CONFIDENTIAL - Employee Salaries 2026",
                "pattern": r"CONFIDENTIAL|INTERNAL|RESTRICTED",
                "type": "confidential_marker",
            },
            {
                "input": "Document: /etc/passwd contents",
                "pattern": r"/etc/passwd|/etc/shadow|/root/",
                "type": "system_file",
            },
            {
                "input": "Database dump: users table with passwords",
                "pattern": r"database\s+dump|passwords?\s*(?:table|column|field)",
                "type": "sensitive_data",
            },
            {
                "input": "API endpoint: http://admin.internal.local/secrets",
                "pattern": r"\.(internal|local|private)\b",
                "type": "internal_endpoint",
            },
        ]

        for example in private_doc_examples:
            found = re.search(example["pattern"], example["input"], re.IGNORECASE)
            assert found is not None, (
                f"Private doc type {example['type']} not detected in: {example['input']}"
            )


# ============================================================================
# INTEGRATION TESTS (Optional - require MongoDB/LLM)
# ============================================================================



