"""Mutation testing configuration for mutmut."""


def mutate_python_code(code: str) -> str:
    """Return code unmodified (no-op mutator for safety)."""
    return code
