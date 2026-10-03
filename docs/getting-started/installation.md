# Installation Guide

This guide covers installing SecondBrain and all required dependencies.

## Standard Installation

### 1. Install from Source (Recommended)

Clone the repository and run the hardware-aware installer. It detects the host
accelerator (NVIDIA CUDA, Intel GPU, Apple Silicon, or CPU-only), installs the
matching torch family (torch + torchvision) from the right index, pins both
exact builds via a pip constraints file, and then installs SecondBrain in
development mode:

```bash
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
./scripts/install.sh
```

Activate your virtual environment first — the script refuses to run outside a
venv/pyenv interpreter and never creates or activates one itself.

Useful flags:

```bash
./scripts/install.sh --dry-run          # show detected target and pip plan, run nothing
./scripts/install.sh --cpu              # force a specific accelerator target
./scripts/install.sh --extras dev,rag   # override the editable-install extras (default: dev)
```

The default extras are `dev`. After installing, verify the detected backend
(the script prints a verdict such as `OK: torch 2.x.x — xpu backend is
available`).

### Manual Installation (CPU-only or custom setup)

If you prefer not to use the script, follow the same three steps it uses:
install the torch-family builds that match your GPU, pin both torch and
torchvision
in a constraints file, then install SecondBrain. The constraint step is not
optional: a plain editable install re-resolves torch and torchvision from
PyPI and silently replaces a locally tagged build (like `+xpu`) with the CUDA
default — pip only keeps the builds you installed when the requirements
explicitly pin their exact versions. torchvision must also come from the same
index as torch: plain-PyPI torchvision is compiled against plain-PyPI torch,
and a pair mixed across build classes breaks at the C-extension level
(`RuntimeError: operator torchvision::nms does not exist`).

**Step 1 — install the torch-family builds for your accelerator:**

```bash
# NVIDIA CUDA (torch and torchvision from PyPI bundle the CUDA runtime)
pip install --upgrade torch torchvision

# Intel GPU / XPU (torch family from the PyTorch XPU index)
pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/xpu

# Apple Silicon (MPS is built into the plain PyPI builds)
pip install --upgrade torch torchvision

# CPU-only
pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**Step 2 — capture the installed builds in a constraints file:**

```bash
python -c 'from importlib.metadata import version; print("torch==" + version("torch")); print("torchvision==" + version("torchvision"))' > /tmp/secondbrain-constraints.txt
```

This records the version pip compares requirements against (the wheel
metadata, e.g. `torch==2.14.0+xpu` and `torchvision==0.29.1+xpu`), not the
runtime `torch.__version__` label, which a PyPI build reports with an extra
suffix (`+cu130`) that the metadata does not contain.

**Step 3 — install SecondBrain against the constraint:**

```bash
pip install --constraint /tmp/secondbrain-constraints.txt -e ".[dev]"
```

If builds with a different accelerator tag are already installed (for example
`torch 2.14.0+cu130` when you target XPU), add `--force-reinstall` to the step
1 command so pip actually replaces them instead of keeping them — for the same
reason, torchvision must be (re)installed from the same index as torch even
when its version number looks unchanged:

```bash
pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/xpu
```

Then re-run step 2 so the constraints file captures the newly installed
builds before the editable install in step 3.

### Intel GPU Prerequisites (XPU)

The torch XPU wheel bundles the compute stack but relies on the host's
level-zero loader. On Ubuntu 24.04+ install it with the Intel compute runtime:

```bash
sudo apt install intel-level-zero-gpu level-zero
```

(Driver setup via `intel-i915-dkms` is only needed if your kernel lacks the
built-in i915/Xe driver.)

SecondBrain then picks the device up automatically:
`SECONDBRAIN_PDF_ACCELERATOR_DEVICE` defaults to `auto`, which selects XPU
when the device is visible; pin it with `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=xpu`
if you want to enforce it.

### 2. Verify Installation

Confirm SecondBrain is installed correctly:

```bash
secondbrain --version
```

Expected output: `secondbrain, version 0.4.0`

## Dependency Overview

SecondBrain depends on several key packages:

| Package | Purpose | Required |
| --------- | --------- | ---------- |
| click | CLI framework | Yes |
| qdrant-client | Qdrant vector database client | Yes |
| aiosqlite / sqlite | SQLite conversation storage | Yes |
| docling | Document parsing | Yes |
| httpx | HTTP client | Yes |
| pydantic, pydantic-settings | Configuration | Yes |
| rich | Terminal output | Yes |
| openai | Embedding provider | Yes |

## Qdrant Setup

SecondBrain uses Qdrant for vector storage and SQLite for conversations/sessions. To get started, run the built-in
Docker management to start the Qdrant service:

```bash
secondbrain start --wait
```

This starts the `secondbrain-qdrant` container with default settings (collection `embeddings`).

If you have Qdrant running elsewhere, point to it via the `SECONDBRAIN_QDRANT_URL` environment variable (for
example `http://localhost:6333`). Conversations and sessions are stored locally in the SQLite database at
`~/.secondbrain/secondbrain.db` — no additional setup is required.

## API Key Configuration

For embedding generation, configure your API key:

```bash
export SECONDBRAIN_OPENAI_API_KEY="your-api-key-here"
```

Alternatively, for OpenAI-compatible providers (Ollama, LM Studio, vLLM):

```bash
export SECONDBRAIN_OPENAI_API_KEY="not-required"
export SECONDBRAIN_OPENAI_BASE_URL="http://localhost:11434/v1"
```

## Verifying Your Setup

Run the health check to verify all services are operational:

```bash
secondbrain health
```

Expected output confirms Qdrant connectivity and service status.

## Uninstalling

To uninstall SecondBrain:

```bash
pip uninstall secondbrain
```

This removes the package but leaves configuration files and data intact.
