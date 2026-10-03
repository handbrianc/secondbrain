#!/usr/bin/env bash
#
# Hardware-aware dependency installer for SecondBrain.
#
# Detects the host accelerator (NVIDIA CUDA, Intel XPU, Apple MPS, or CPU-only)
# and installs the matching torch FAMILY (torch + torchvision) FIRST, from the
# right index. The two must come from the same index: plain-PyPI torchvision is
# compiled against plain-PyPI torch, and a pair mixed across build classes
# breaks at the C-extension level ("RuntimeError: operator torchvision::nms
# does not exist"). The exact installed builds are then pinned via a pip
# constraints file, so the editable install keeps them instead of silently
# swapping either for whatever PyPI serves by default (pip re-resolves torch
# from PyPI and ignores locally tagged versions like +xpu unless the
# requirement pins the exact local version).
#
# Usage: scripts/install.sh [--cpu|--cuda|--xpu|--mps] [--dry-run] [--extras EXTRA]
#
# Needs an activated virtual environment or a pyenv interpreter (override the
# interpreter with PYTHON=...); it never creates or activates a venv itself
# (AGENTS.md rule). Note: torch is large (up to ~2-3 GB for CUDA builds), so
# the first run may take a while.

set -euo pipefail

readonly XPU_INDEX="https://download.pytorch.org/whl/xpu"
readonly CPU_INDEX="https://download.pytorch.org/whl/cpu"
readonly DEFAULT_EXTRAS="dev"
# torch and torchvision are installed and pinned as a unit (see header):
# they must come from the same index or their compiled ops do not match.
readonly -a TORCH_FAMILY=(torch torchvision)

PYTHON="${PYTHON:-python3}"
TARGET=""          # forced target from --cpu/--cuda/--xpu/--mps; empty = auto-detect
DRY_RUN=0
EXTRAS="$DEFAULT_EXTRAS"
INSTALLED_VERSIONS=()   # INSTALLED_VERSIONS[i] = installed version of TORCH_FAMILY[i] ("" = absent)
PKG_MODES=()            # PKG_MODES[i] = "upgrade" | "force" for TORCH_FAMILY[i]
PKG_REASONS=()          # PKG_REASONS[i] = human-readable rationale for PKG_MODES[i]
PKG_GROUP=()            # scratch: family members grouped by install mode
CMD=()                  # scratch: pip command currently being built

die()   { echo "ERROR: $*" >&2; exit 1; }
info()  { echo "==> $*"; }
banner(){ echo; echo "======== $* ========"; }

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [--cpu|--cuda|--xpu|--mps] [--dry-run] [--extras EXTRA]

Installs SecondBrain with torch + torchvision builds matched to the host GPU.
The two must come from the same index (their compiled ops are built against
each other), and the installed builds are pinned via a pip constraints file so
the editable install keeps them instead of replacing either with PyPI's
default build.

Options:
  --cpu|--cuda|--xpu|--mps  Force the accelerator target. The torch-family
                            index is the PyTorch XPU/CPU index for xpu/cpu,
                            plain PyPI for cuda/mps.
  --dry-run                 Print the detected target, index and pip commands
                            (including the stage-2 torch/torchvision pins);
                            run nothing.
  --extras EXTRA            Comma-separated extras for `pip install -e ".[EXTRAS]"` (default: dev).
  --help                    Show this help and exit.

Without a target flag the accelerator is auto-detected:
  1. NVIDIA GPU (nvidia-smi, or an NVIDIA VGA/3D device in lspci) -> cuda
  2. Intel GPU and the level-zero loader (libze_loader) installed -> xpu
  3. macOS (Darwin)                                              -> mps
  4. anything else                                               -> cpu

Environment: PYTHON=...  Interpreter to install with (default: python3).
Activate your virtual environment first; this script intentionally does not
create or activate one.
EOF
}

# --- Argument parsing (flags only; anything else is a usage error) ------------
while [ $# -gt 0 ]; do
  case "$1" in
    --cpu|--cuda|--xpu|--mps)
      TARGET="${1#--}"
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --extras)
      [ $# -ge 2 ] || die "--extras requires a value"
      EXTRAS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      echo "Valid flags: --cpu --cuda --xpu --mps --dry-run --extras EXTRA --help" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# --- Environment guard --------------------------------------------------------
# AGENTS.md anti-pattern: scripts must not auto-create or activate venvs, so
# refuse to run outside a venv / pyenv interpreter.
banner "Environment check"
PY_BIN="$(command -v "$PYTHON")" || die "Interpreter '$PYTHON' not found on PATH"

# Accept pyenv shims/interpreters, an active $VIRTUAL_ENV, or any interpreter
# that resolves inside a virtualenv (sys.prefix != sys.base_prefix).
venv_ok=0
case "$PY_BIN" in *pyenv/shims/*|*pyenv/versions/*) venv_ok=1 ;; esac
# Validate the selected interpreter below; PYTHON may override the active environment.
if [ "$venv_ok" -eq 0 ] \
   && "$PY_BIN" -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' >/dev/null 2>&1; then
  venv_ok=1
fi
if [ "$venv_ok" -ne 1 ]; then
  die "No active virtual environment detected. Activate your venv first (e.g. 'source .venv/bin/activate') or use a pyenv interpreter; this script never creates or activates environments itself."
fi
info "Using interpreter: $PY_BIN"

# --- Accelerator detection (only when no target flag was given) ---------------
# NOTE: tool output is captured into variables and matched with bash built-ins
# instead of `tool | grep -q` pipelines. Under `set -o pipefail`, grep -q
# exiting early on a match can SIGPIPE the upstream tool (e.g. the large
# `ldconfig -p` listing), turning a successful detection into a spurious
# failure that would silently fall through to the next rule.
detect_target() {
  local lspci_out="" ldconfig_out=""
  # tr (not ${var,,}) for bash 3.2 compatibility — macOS ships bash 3.2.
  # tr consumes all input, so no pipefail/SIGPIPE hazard here.
  if command -v lspci >/dev/null 2>&1; then
    lspci_out="$(lspci 2>/dev/null | tr '[:upper:]' '[:lower:]' || true)"
  fi
  if command -v ldconfig >/dev/null 2>&1; then
    ldconfig_out="$(ldconfig -p 2>/dev/null || true)"
  fi

  # 1. Identify GPU vendors, requiring the vendor and display class on one line.
  local pci_line has_nvidia_gpu=0 has_intel_gpu=0
  while IFS= read -r pci_line; do
    if [[ "$pci_line" =~ nvidia ]] && [[ "$pci_line" =~ vga|3d ]]; then
      has_nvidia_gpu=1
    elif [[ "$pci_line" =~ intel ]] && [[ "$pci_line" =~ vga|3d|display ]]; then
      has_intel_gpu=1
    fi
  done <<< "$lspci_out"
  if command -v nvidia-smi >/dev/null 2>&1 || [ "$has_nvidia_gpu" -eq 1 ]; then echo "cuda"; return; fi
  # 2. Intel XPU also requires the level-zero loader.
  if [ "$has_intel_gpu" -eq 1 ] && [[ "$ldconfig_out" == *libze_loader* ]]; then echo "xpu"; return; fi
  # 3. macOS: MPS is built into the plain PyPI torch/torchvision builds.
  if [ "$(uname -s)" = "Darwin" ]; then echo "mps"; return; fi
  # 4. Everything else: CPU.
  echo "cpu"
}

banner "Accelerator detection"
if [ -n "$TARGET" ]; then
  info "Target forced by flag: $TARGET"
else
  TARGET="$(detect_target)"
  info "Auto-detected target: $TARGET"
fi

case "$TARGET" in
  xpu)      INDEX="$XPU_INDEX" ;;
  cpu)      INDEX="$CPU_INDEX" ;;
  cuda|mps) INDEX="" ;;   # plain PyPI (CUDA bundled on NVIDIA, MPS built in on macOS)
  *)        die "internal error: unknown target '$TARGET'" ;;
esac

# --- Decide how each torch-family package must be (re)installed ---------------
# torch and torchvision move as a unit (same index, matching compiled ops),
# but each package gets its own install mode based on the build tag it has
# right now. The installed version's local segment (the "+tag": xpu, cpu,
# cu130, or none for a plain PyPI build) is compared against the target — xpu
# needs +xpu, cpu needs +cpu, cuda accepts no tag (plain PyPI bundles the CUDA
# runtime) or cu*, mps expects no tag. A missing package counts as a mismatch
# (it gets installed); a tag mismatch needs --force-reinstall, because pip
# would otherwise keep the installed build and ignore the new --index-url.
#
# Versions are read from distribution METADATA (importlib.metadata), not by
# importing the packages: importing a mismatched torchvision can fail outright
# (the nms error this script exists to avoid), and the metadata version is
# exactly what pip compares constraints against (see step 2 below).

# Prints the installed version of $1 ("" when the package is absent; never
# fails, so callers can treat an empty result as "not installed").
installed_version() {
  "$PY_BIN" -c '
import sys
from importlib.metadata import PackageNotFoundError, version
try:
    print(version(sys.argv[1]))
except PackageNotFoundError:
    pass
' "$1" 2>/dev/null || true
}

# (Re)fills INSTALLED_VERSIONS from the current environment.
read_installed_versions() {
  local i
  for i in "${!TORCH_FAMILY[@]}"; do
    INSTALLED_VERSIONS[i]="$(installed_version "${TORCH_FAMILY[i]}")"
  done
}

# Prints the local build tag of a version string ("" when the build has none).
local_tag() {
  case "$1" in
    *+*) printf '%s' "${1##*+}" ;;
  esac
}

tag_matches_target() {
  # $1 = target, $2 = local version segment ("" when the build has none)
  case "$1" in
    xpu)  [ "$2" = "xpu" ] ;;
    cpu)  [ "$2" = "cpu" ] ;;
    cuda) { [ -z "$2" ] || case "$2" in cu*) true ;; *) false ;; esac; } ;;
    mps)  [ -z "$2" ] ;;   # plain PyPI build
  esac
}

# Human-readable label for a PKG_MODES value.
mode_label() {
  case "$1" in
    upgrade) echo "upgrade" ;;
    force)   echo "upgrade+force-reinstall" ;;
  esac
}

read_installed_versions
for i in "${!TORCH_FAMILY[@]}"; do
  pkg="${TORCH_FAMILY[i]}"
  ver="${INSTALLED_VERSIONS[i]}"
  if [ -z "$ver" ]; then
    PKG_MODES[i]=force
    PKG_REASONS[i]="package not installed"
  else
    tag="$(local_tag "$ver")"
    if tag_matches_target "$TARGET" "$tag"; then
      PKG_MODES[i]=upgrade
      PKG_REASONS[i]="installed build tag '${tag:-none}' matches target '$TARGET'"
    else
      PKG_MODES[i]=force
      PKG_REASONS[i]="installed build tag '${tag:-none}' does not match target '$TARGET'"
    fi
  fi
done

# Fills CMD with the stage-1 pip command for one install mode ($1: "upgrade"
# or "force"); returns 1 when no family member needs that mode. Members
# sharing a mode install in ONE pip command, so e.g. a tag-matching torch
# (plain --upgrade) next to a mismatched torchvision (--force-reinstall)
# produce two commands. Every family member is covered by exactly one command.
stage1_cmd_for_mode() {
  local mode="$1" i
  PKG_GROUP=()
  for i in "${!TORCH_FAMILY[@]}"; do
    if [ "${PKG_MODES[i]}" = "$mode" ]; then PKG_GROUP+=( "${TORCH_FAMILY[i]}" ); fi
  done
  if [ "${#PKG_GROUP[@]}" -eq 0 ]; then return 1; fi
  CMD=( "$PY_BIN" -m pip install --upgrade )
  if [ "$mode" = "force" ]; then CMD+=( --force-reinstall ); fi
  CMD+=( "${PKG_GROUP[@]}" )
  if [ -n "$INDEX" ]; then CMD+=( --index-url "$INDEX" ); fi
}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "$EXTRAS" ]; then
  PROJECT_CMD=( "$PY_BIN" -m pip install -e "${PROJECT_ROOT}[$EXTRAS]" )
else
  PROJECT_CMD=( "$PY_BIN" -m pip install -e "$PROJECT_ROOT" )
fi

# Device check run after install: prints "<version> <is_available>".
case "$TARGET" in
  xpu)  CHECK='import torch; print(torch.__version__, torch.xpu.is_available())' ;;
  cuda) CHECK='import torch; print(torch.__version__, torch.cuda.is_available())' ;;
  mps)  CHECK='import torch; print(torch.__version__, torch.backends.mps.is_available())' ;;
  cpu)  CHECK='import torch; print(torch.__version__)' ;;
esac

# --- Dry run: report the plan and exit ----------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  banner "Dry run (nothing will be executed)"
  info "Target:              $TARGET"
  info "Torch-family index:  ${INDEX:-plain PyPI (no --index-url)}"
  info "Extras:              ${EXTRAS:-<none>}"
  for i in "${!TORCH_FAMILY[@]}"; do
    pkg="${TORCH_FAMILY[i]}"
    tag="$(local_tag "${INSTALLED_VERSIONS[i]}")"
    info "$(printf '%-20s' "${pkg}:") installed ${INSTALLED_VERSIONS[i]:-<none>}, tag '${tag:-none}', mode: $(mode_label "${PKG_MODES[i]}"), index: ${INDEX:-plain PyPI} — ${PKG_REASONS[i]}"
  done
  info "Stage 2 pins:        constraint file (torch==<installed by step 1>, torchvision==<installed by step 1> — captured at runtime)"
  for mode in upgrade force; do
    if stage1_cmd_for_mode "$mode"; then
      echo "  Would run: ${CMD[*]}"
    fi
  done
  echo "  Would run: ${PROJECT_CMD[*]} --constraint <constraints file: torch==<installed>, torchvision==<installed>>"
  echo "  Would run: $PY_BIN -c '$CHECK'"
  exit 0
fi

# --- Stage 1: install the torch family from the target index -------------------
banner "Step 1/2: torch family ($TARGET build)"
info "Index: ${INDEX:-plain PyPI}"
for i in "${!TORCH_FAMILY[@]}"; do
  info "$(printf '%-12s' "${TORCH_FAMILY[i]}:") $(mode_label "${PKG_MODES[i]}") — ${PKG_REASONS[i]}"
done
for mode in upgrade force; do
  if stage1_cmd_for_mode "$mode"; then
    "${CMD[@]}"
  fi
done

# --- Stage 2: install the project in editable mode -----------------------------
# pip re-resolves every requirement — torch and torchvision included — from
# PyPI during this install, and a fresh resolution ignores locally tagged
# builds like 2.14.1+xpu unless the requirement explicitly pins that exact
# version. The constraints file below pins EVERY torch-family member to <what
# step 1 just installed>, which is the only way to keep the accelerator
# builds; without it pip silently swaps torch for PyPI's default (observed in
# the field: +xpu -> +cu130) and upgrades torchvision to a plain-PyPI build
# whose compiled ops do not match the installed torch (observed in the field:
# "operator torchvision::nms does not exist").
banner "Step 2/2: SecondBrain (extras: ${EXTRAS:-none})"
# Capture the version pip itself compares constraints against: the installed
# distribution's metadata — for EVERY family member. torch.__version__ is NOT
# that — plain-PyPI (CUDA) wheels report e.g. "2.14.0+cu130" at runtime while
# their metadata says "2.14.0", so a pin built from __version__ can match
# nothing and stage 2 fails. XPU/CPU wheels carry the local tag in both
# places, so the metadata version is correct for every target.
read_installed_versions
CONSTRAINTS_FILE="$(mktemp "${TMPDIR:-/tmp}/secondbrain-constraints.XXXXXX")"
trap 'rm -f "$CONSTRAINTS_FILE"' EXIT
: > "$CONSTRAINTS_FILE"
PINS=""
for i in "${!TORCH_FAMILY[@]}"; do
  pkg="${TORCH_FAMILY[i]}"
  ver="${INSTALLED_VERSIONS[i]}"
  if [ -z "$ver" ]; then
    die "could not read the installed $pkg version right after step 1 (see pip output above)"
  fi
  printf '%s==%s\n' "$pkg" "$ver" >> "$CONSTRAINTS_FILE"
  PINS="$PINS $pkg==$ver"
done
info "Pinning${PINS} via constraint file (prevents pip from swapping any family build back to PyPI's)"
PROJECT_CMD+=( --constraint "$CONSTRAINTS_FILE" )
"${PROJECT_CMD[@]}"

# --- Verification: import torch, report version + target-device availability ---
banner "Verification"
VERIFY_OUT="$("$PY_BIN" -c "$CHECK")" || die "torch failed to import after installation"
case "$VERIFY_OUT" in
  *" True")
    info "OK: torch ${VERIFY_OUT% *} — $TARGET backend is available"
    ;;
  *" False")
    die "torch ${VERIFY_OUT% *} installed, but no $TARGET device is visible — docling would fall back to CPU (check drivers/runtime, or pin SECONDBRAIN_PDF_ACCELERATOR_DEVICE accordingly)"
    ;;
  *)
    info "OK: torch $VERIFY_OUT (CPU build — no device check needed)"
    ;;
esac

banner "Done"
info "Next steps: 'secondbrain --version' then 'secondbrain health'"
