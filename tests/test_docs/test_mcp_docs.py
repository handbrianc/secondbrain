"""Documentation completeness tests for the MCP server README.

The MCP server's README (`mcp-server/README.md`) documents the exposed feature
set. These tests keep it honest against the code's sources of truth: the tool
functions registered via `#[tool(...)]` attributes in
`mcp-server/src/tools/*.rs`, and the `SECONDBRAIN_MCP_*` variables parsed by
`mcp-server/src/config.rs`.

Every registered tool name and every server variable must appear in the
README's reference tables (a table row anchored on the backticked name, not
just a passing prose mention). A new tool or variable that lands without
documentation fails here — that is the drift alarm this module exists for.

The module also guards the docs-site integration (`add-mcp-docs-site-integration`):
the MkDocs navigation must link the MCP guide (`docs/developer-guide/mcp.md`),
and the Docker guide must describe the MCP-server-primary container with no
stale "application runs natively / Docker only for Qdrant" framing.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
README_PATH = MCP_DIR / "README.md"
CONFIG_PATH = MCP_DIR / "src" / "config.rs"
TOOLS_DIR = MCP_DIR / "src" / "tools"
MKDOCS_PATH = REPO_ROOT / "mkdocs.yml"
DOCKER_GUIDE_PATH = REPO_ROOT / "docs" / "developer-guide" / "docker.md"

# Known surface elements, used as canaries against parser rot: if the parser
# stops finding these, the drift alarm is blind and the test must fail loudly.
# New tools/variables are picked up automatically and must then be documented.
KNOWN_TOOLS = [
    "search",
    "ingest_documents",
    "chat_send",
    "chat_list_sessions",
    "chat_get_history",
]
KNOWN_VARIABLES = [
    "SECONDBRAIN_MCP_HTTP_BIND_ADDR",
    "SECONDBRAIN_MCP_HTTP_TLS_ENABLED",
    "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH",
    "SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH",
    "SECONDBRAIN_MCP_AUTH_TOKEN",
    "SECONDBRAIN_MCP_CLI_BIN",
    "SECONDBRAIN_MCP_WORKSPACE_ROOT",
    "SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS",
    "SECONDBRAIN_MCP_LOG_LEVEL",
]

# Registration attributes: `#[tool(...)]` (possibly multiline) or the bare
# `#[tool]`. `#[tool_router(...)` deliberately does not match — routers are
# not tools.
_TOOL_ATTRIBUTE = re.compile(r"#\[tool(?:\(|\])")
_FN_SIGNATURE = re.compile(r"\bfn\s+([a-z_][a-z0-9_]*)")
_MCP_VARIABLE = re.compile(r'"(SECONDBRAIN_MCP_[A-Z0-9_]+)"')


def _read(path: Path) -> str:
    """Reads a source file, failing with its path when it is missing."""
    return path.read_text(encoding="utf-8")


def _registered_tools(source: str) -> list[str]:
    """Extracts the tool function names registered via `#[tool]` attributes.

    The attribute's parentheses are balanced by hand (descriptions contain
    balanced parentheses such as ``(created: ...)``), then the next function
    signature after the attribute is the registered tool name.
    """
    names: list[str] = []
    for match in _TOOL_ATTRIBUTE.finditer(source):
        if match.group(0).endswith("]"):
            # Bare `#[tool]`: no arguments to balance.
            attribute_end = match.end()
        else:
            depth = 1
            i = match.end()
            while i < len(source) and depth > 0:
                if source[i] == "(":
                    depth += 1
                elif source[i] == ")":
                    depth -= 1
                i += 1
            attribute_end = i
        signature = _FN_SIGNATURE.search(source[attribute_end : attribute_end + 2000])
        if signature:
            names.append(signature.group(1))
    return names


def _config_variables(source: str) -> list[str]:
    """Extracts every `SECONDBRAIN_MCP_*` string literal in the config source."""
    return sorted(set(_MCP_VARIABLE.findall(source)))


def _has_table_row(document: str, name: str) -> bool:
    """Whether `name` appears as a backticked first cell of a table row.

    Anchoring on a table row (instead of any substring) is what makes the
    check meaningful: ``search`` in prose is trivially present everywhere, a
    `| `search` |` reference-table row means the tool is actually documented.
    """
    pattern = rf"^\|\s*`{re.escape(name)}`\s*\|"
    return re.search(pattern, document, re.MULTILINE) is not None


def test_every_registered_tool_is_documented() -> None:
    """Every tool registered in the source tree has a README reference row."""
    sources = "".join(_read(path) for path in sorted(TOOLS_DIR.glob("*.rs")))
    tools = _registered_tools(sources)

    missing_canaries = [name for name in KNOWN_TOOLS if name not in tools]
    assert not missing_canaries, (
        "the tool-name parser stopped finding known tools — fix the parser "
        f"before trusting the drift alarm: {missing_canaries}"
    )
    assert tools, "no registered tools were parsed from the tool modules"

    readme = _read(README_PATH)
    undocumented = [name for name in tools if not _has_table_row(readme, name)]
    assert not undocumented, (
        "tools registered in mcp-server/src/tools/ are missing their README "
        f"tool-reference row: {undocumented}"
    )


def test_every_config_variable_is_documented() -> None:
    """Every SECONDBRAIN_MCP_* variable parsed from the config has a README row."""
    variables = _config_variables(_read(CONFIG_PATH))

    missing_canaries = [name for name in KNOWN_VARIABLES if name not in variables]
    assert not missing_canaries, (
        "the variable parser stopped finding known SECONDBRAIN_MCP_* "
        f"variables — fix the parser before trusting the drift alarm: {missing_canaries}"
    )
    assert variables, "no SECONDBRAIN_MCP_* variables were parsed from config.rs"

    readme = _read(README_PATH)
    undocumented = [name for name in variables if not _has_table_row(readme, name)]
    assert not undocumented, (
        "SECONDBRAIN_MCP_* variables parsed from src/config.rs are missing "
        f"their README configuration row: {undocumented}"
    )


def test_readme_cross_links_the_design_doc_and_smoke() -> None:
    """The README links the scaffold design doc and the e2e smoke as verification."""
    readme = _read(README_PATH)

    assert "add-mcp-server-scaffold/design.md" in readme, (
        "the README must link the server design doc "
        "(openspec/changes/add-mcp-server-scaffold/design.md)"
    )
    assert "scripts/mcp_e2e_smoke.sh" in readme, (
        "the README must name scripts/mcp_e2e_smoke.sh as the verification entry point"
    )


def test_mkdocs_nav_links_the_mcp_page() -> None:
    """The MkDocs navigation includes the MCP guide page."""
    mkdocs = _read(MKDOCS_PATH)

    nav_entry_lines = [
        line for line in mkdocs.splitlines() if "developer-guide/mcp.md" in line
    ]
    assert nav_entry_lines, (
        "mkdocs.yml's navigation must include the MCP guide "
        "(docs/developer-guide/mcp.md); a nav line naming it was not found"
    )


def test_docker_guide_describes_the_mcp_primary_container() -> None:
    """The Docker guide describes the MCP-server-primary stack, not the old one.

    The stale framing (``add-mcp-docs-site-integration``): SecondBrain used
    Docker "primarily for Qdrant" with "the application itself runs natively".
    The guide must instead describe the container whose primary function is
    the MCP server, the CLI companion service, and the env-file configuration.
    """
    guide = _read(DOCKER_GUIDE_PATH)

    stale_framings = [
        "primarily for Qdrant",
        "runs natively",
    ]
    stale = [phrase for phrase in stale_framings if phrase in guide]
    assert not stale, (
        "docs/developer-guide/docker.md still carries the stale "
        f"pre-MCP framing: {stale}"
    )

    required = [
        "secondbrain-mcp",  # the container's primary function
        "companion",  # the cli companion service (and the qdrant companion)
        ".env.docker",  # the env-file configuration contract
    ]
    missing = [marker for marker in required if marker not in guide]
    assert not missing, (
        "docs/developer-guide/docker.md must describe the MCP-primary "
        f"container stack; these markers are missing: {missing}"
    )
