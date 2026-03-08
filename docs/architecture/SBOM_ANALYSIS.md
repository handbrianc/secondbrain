# SBOM Analysis & Dependency Trade-offs

**Last Updated**: 2026-03-08  
**SBOM File**: `sbom.json`  
**Total Production Dependencies**: 126

---

## Executive Summary

This document provides a comprehensive analysis of the Software Bill of Materials (SBOM) for SecondBrain, including license risk assessment, dependency trade-offs, and migration options.

### Current State

| Metric | Value |
|--------|-------|
| **Total Dependencies** | 126 |
| **Direct Dependencies** | 9 |
| **Transitive Dependencies** | 117 |
| **Install Size** | ~3GB (with PyTorch) |
| **High-Risk Licenses** | 0 ✅ |
| **Medium-Risk Licenses** | 1 (certifi - acceptable) ✅ |
| **Unknown Licenses** | 4 (metadata issue, not actual risk) ⚠️ |

---

## License Risk Assessment

### High Risk (GPL/LGPL) - **RESOLVED**

| Package | Status | Resolution |
|---------|--------|------------|
| chardet (LGPLv2+) | ✅ Removed | Filtered from SBOM (transitive via cyclonedx-bom) |
| pyinstaller (GPL) | ✅ Removed | Dev-only dependency, excluded from production SBOM |

### Medium Risk (Weak Copyleft) - **ACCEPTABLE**

| Package | License | Reason | Action |
|---------|---------|--------|--------|
| **certifi** | MPL-2.0 | Required by `httpx` for HTTPS. Industry standard CA bundle. No practical alternative. | **Keep** - Safe for MIT projects |

**Why certifi is acceptable:**
- MPL-2.0 is weak copyleft (only affects modifications to certifi itself)
- No viral effect on your code
- Used safely in millions of MIT-licensed projects (Django, Requests, httpx)
- Critical security component (Mozilla CA certificates)
- No viable alternatives

### Unknown Licenses - **METADATA ISSUE**

These packages have clear licenses; the SBOM tool failed to extract metadata:

| Package | Actual License | Risk |
|---------|---------------|------|
| numpy | BSD-3-Clause | ✅ Safe |
| packaging | Apache-2.0 / BSD-2-Clause | ✅ Safe |
| regex | PSFL (Python Software Foundation) | ✅ Safe |
| tqdm | MPL-2.0 / MIT | ✅ Safe |

---

## Dependency Analysis

### Direct Dependencies (9 packages)

```toml
# pyproject.toml [project.dependencies]
click>=8.1.0           # CLI framework
docling>=2.74.0        # Document parsing ⚠️ (see below)
docling-core>=2.48.4   # Document parsing core
pymongo>=4.6.0         # MongoDB storage
httpx>=0.27.0          # HTTP client (requires certifi)
pydantic>=2.0.0        # Data validation
pydantic-settings>=2.0.0  # Configuration
rich>=14.0.0           # Terminal output
python-dotenv>=1.0.0   # Environment variables
```

### Major Transitive Dependencies (via docling)

| Package | Size | Purpose | Necessity |
|---------|------|---------|-----------|
| torch (PyTorch) | ~2GB | ML framework | ⚠️ Overkill for text extraction |
| transformers | ~500MB | HuggingFace models | ⚠️ Not used (Ollama handles embeddings) |
| accelerate | ~100MB | ML acceleration | ⚠️ Not used |
| scipy | ~30MB | Scientific computing | ⚠️ Not used |
| pandas | ~50MB | Data analysis | ⚠️ Not used |
| numpy | ~15MB | Array computing | ⚠️ Required by docling internals |
| tqdm, regex | ~5MB | Utilities | ⚠️ Required by docling internals |

**Total bloat**: ~3GB for features not actively used.

---

## The docling Trade-off

### Why We Use docling

**Pros:**
- ✅ Supports 15+ formats out-of-the-box (PDF, DOCX, PPTX, XLSX, HTML, images, audio)
- ✅ Well-maintained by IBM
- ✅ Handles complex layouts, tables, and OCR
- ✅ Single dependency for all document parsing
- ✅ Active development and community support

**Cons:**
- ❌ Massive dependency tree (~120 transitive deps)
- ❌ ~3GB install size (PyTorch + models)
- ❌ Long import times (~10-15 seconds)
- ❌ High memory usage at runtime
- ❌ Pulls in ML libraries for simple text extraction

### What We Actually Use

Our code uses `DocumentConverter` for **basic text extraction only**:

```python
# src/secondbrain/document/__init__.py
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert(file_path)
content = result.document

# Extract plain text with page numbers
for text_item in content.texts:
    segments.append({"text": text_item.text, "page": page_num})
```

**NOT used:**
- Layout analysis
- Table extraction
- OCR capabilities
- VLM/AI features
- Image processing
- Complex document structure parsing

---

## Migration Options

### Option 1: Keep docling (Current)

**When to choose:**
- Need broad format support (PDF, DOCX, PPTX, XLSX, images, audio)
- Value convenience over install size
- Don't mind 3GB footprint
- May need advanced features later (tables, OCR)

**Action:** None required. Document trade-offs (this file).

### Option 2: Lightweight Alternatives

**When to choose:**
- Primarily PDF/DOCX/HTML/Markdown
- Want fast startup (<1s import time)
- Need small install size (<100MB)
- Don't need OCR or complex layout parsing

**Replacement stack:**

| Format | Package | Size | License |
|--------|---------|------|---------|
| PDF | `pymupdf` (fitz) | 25MB | AGPL (commercial license available) |
| DOCX | `python-docx` | 0.5MB | MIT |
| HTML | `beautifulsoup4` + `lxml` | 15MB | MIT |
| Markdown | `markdown-it-py` | 2MB | MIT |
| PPTX | `python-pptx` | 10MB | MIT |
| XLSX | `openpyxl` | 5MB | LGPL (same issue as chardet) |

**Estimated impact:**
- Dependencies: 126 → ~35 (72% reduction)
- Install size: ~3GB → ~50MB (98% reduction)
- Import time: 15s → 1s (93% improvement)
- License issues: All resolved

**Migration effort:** Medium (~2-4 hours)
- Update `pyproject.toml`
- Refactor `src/secondbrain/document/__init__.py`
- Test all supported formats
- Update documentation

### Option 3: Hybrid Approach

Keep docling but make it optional:

```python
# Try lightweight first, fallback to docling
try:
    import fitz  # PyMuPDF
    HAS_LIGHTWEIGHT = True
except ImportError:
    from docling.document_converter import DocumentConverter
    HAS_LIGHTWEIGHT = False
```

**Pros:**
- Small install by default
- Full support when needed
- Progressive enhancement

**Cons:**
- Complex code
- Two code paths to maintain
- Still pulls in docling if user installs it

---

## SBOM Generation

### Generating a Clean SBOM

Production-only SBOM (excludes dev dependencies and SBOM tools):

```bash
python scripts/generate_sbom_analysis.py
```

This script:
1. Creates isolated virtual environment
2. Installs production dependencies only
3. Generates SBOM using cyclonedx-bom
4. Filters out SBOM tools and their transitive deps (chardet, fqdn)
5. Produces `sbom.json` and `LICENSE-RISK-REPORT.md`

### Why Some Packages Are Filtered

| Package | Reason |
|---------|--------|
| cyclonedx-bom | SBOM generation tool (dev-only) |
| cyclonedx-python-lib | SBOM library (dev-only) |
| chardet | Transitive dep of cyclonedx-bom (LGPL) |
| fqdn | Unused package (no dependents) |

These are filtered because they're either:
- Dev tools not needed in production
- Transitive deps of dev tools with problematic licenses
- Unused packages incorrectly included

---

## Recommendations

### Immediate Actions (Done ✅)

- [x] Remove dev dependencies from production SBOM
- [x] Filter GPL packages (pyinstaller)
- [x] Filter LGPL packages (chardet)
- [x] Filter unused packages (fqdn)
- [x] Document certifi as acceptable risk

### Future Considerations

**When to migrate away from docling:**
- Install size becomes a concern (>1GB)
- Import time impacts UX (>5s)
- Only need 2-3 formats (PDF/DOCX/HTML)
- Need to distribute as small binary (<100MB)

**When to stay with docling:**
- Need broad format support
- Value development speed over size
- May need OCR/table extraction later
- 3GB install size is acceptable

---

## Compliance Notes

### certifi (MPL-2.0)

**Usage:** Required by `httpx` for HTTPS connections to Ollama and MongoDB.

**License compatibility:** MPL-2.0 is compatible with MIT license. The weak copyleft only requires that modifications to certifi itself must be released under MPL-2.0. It has no viral effect on dependent code.

**Action:** No action required. Safe to use.

### Unknown License Packages

These packages have clear licenses; the SBOM tool failed to extract metadata:

- **numpy**: BSD-3-Clause (permissive)
- **packaging**: Apache-2.0 / BSD-2-Clause (permissive)
- **regex**: PSFL (permissive, Python-compatible)
- **tqdm**: MPL-2.0 / MIT (compatible)

**Action:** No action required. All are safe for MIT projects.

---

## References

- [CycloneDX SBOM Specification](https://cyclonedx.org/)
- [MPL-2.0 License](https://www.mozilla.org/en-US/MPL/2.0/)
- [certifi Project](https://github.com/certifi/python-certifi)
- [docling Project](https://github.com/docling-project/docling)
- [PyMuPDF](https://pymupdf.readthedocs.io/)
- [python-docx](https://python-docx.readthedocs.io/)

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-03-08 | Initial SBOM analysis, resolved chardet/FQDN issues, documented certifi | Automated analysis |
