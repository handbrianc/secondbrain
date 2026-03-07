# License Risk Report

**Project**: secondbrain  
**Generated**: 2026-03-07 00:28:51  
**SBOM File**: sbom.json

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Dependencies** | 181 |
| **Unique Licenses** | 18 |
| **Unknown Licenses** | 5 |
| **High Risk Packages** | 3 |
| **Medium Risk Packages** | 3 |
| **Low Risk Packages** | 170 |

### Overall Risk Assessment: **REQUIRES REVIEW**

- **3 packages** use strong copyleft licenses (GPL/LGPL) requiring attention
- **3 packages** use weak copyleft licenses (MPL)
- **5 packages** have unknown licenses requiring manual review
- 170 packages use permissive licenses (MIT, BSD, Apache, ISC)

---

## Risk Classification

### HIGH RISK (Strong Copyleft)

**Count**: 3 packages

> **Impact**: These licenses require derivative works to be open-sourced under the same license terms.

| Package | Version | License | Concern |
|---------|---------|---------|---------|
| pyinstaller | 6.19.0 | GPL-2.0-only | Strong copyleft - GPL requires open source |
| pyinstaller-hooks-contrib | 2026.1 | GPL-2.0-only | Strong copyleft - GPL requires open source |
| chardet | 5.2.0 | License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+) | Copyleft - may affect distribution |

### MEDIUM RISK (Weak Copyleft)

**Count**: 3 packages

> **Impact**: These licenses have weaker copyleft requirements, typically file-level.

| Package | Version | License | Concern |
|---------|---------|---------|---------|
| fqdn | 1.5.1 | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft - review distribution model |
| pathspec | 1.0.4 | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft - review distribution model |
| certifi | 2026.2.25 | MPL-2.0 | Weak copyleft - review distribution model |

### LOW RISK (Permissive)

**Count**: 170 packages

#### License Distribution

| License | Packages | Risk Level | Notes |
|---------|----------|------------|-------|
| MIT | 99 | Low | Permissive, commercial-friendly |
| BSD-3-Clause | 18 | Low | Permissive, OSI-approved |
| Apache-2.0 | 14 | Low | Permissive, OSI-approved |
| BSD License | 12 | Low | Permissive, OSI-approved |
| Apache Software License | 12 | Low | Permissive, OSI-approved |
| ISC | 4 | Low | Permissive, similar to MIT |
| BSD-2-Clause | 3 | Low | Permissive, OSI-approved |
| PSF-2.0 | 2 | Low | Permissive |
| declared license of 'antlr4-python3-runtime' | 1 | Low | Permissive |
| Python-2.0 | 1 | Low | Permissive |
| MIT-CMU | 1 | Low | Permissive, commercial-friendly |
| declared license of 'pypdfium2' | 1 | Low | Permissive |
| declared license of 'sentinels' | 1 | Low | Permissive |
| declared license file: LICENSE | 1 | Low | Permissive |

---

## Packages Requiring Manual Review

**Count**: 5

The following packages have unknown or missing license metadata. **Manual verification required**:

- **cryptography@46.0.5** - Check PyPI page or repository
- **numpy@2.4.2** - Check PyPI page or repository
- **packaging@26.0** - Check PyPI page or repository
- **regex@2026.2.19** - Check PyPI page or repository
- **tqdm@4.67.3** - Check PyPI page or repository

### Recommended Actions for Unknown Licenses:

1. Visit PyPI: https://pypi.org/p/{package_name}/
2. Check the project's LICENSE file in source repository (GitHub/GitLab)
3. Contact package maintainer if unclear
4. Consider filing issue to add license metadata

---

## Compliance Status

### WARNING: Copyleft Licenses Detected

**3 packages** use GPL/LGPL licenses that may affect your distribution model:

- **pyinstaller** (GPL-2.0-only) - Used for building executables; safe for internal builds
- **pyinstaller-hooks-contrib** (GPL-2.0-only) - Extension for PyInstaller
- **chardet** (LGPLv2+) - Character encoding detector; LGPL allows linking

### PASSED: No Proprietary Licenses
No commercial/proprietary licenses requiring paid licensing fees.

### WARNING: Unknown Licenses
5 packages require manual license verification before production deployment.

---

## Recommendations

### Immediate Actions (Priority: HIGH)

1. **Review GPL/LGPL Dependencies**
   - **PyInstaller**: Safe for internal builds/binaries, but GPL applies if distributed
   - **chardet (LGPL)**: Safe for linking; verify if you modify the library
   - **Decision needed**: Continue using or find permissive alternatives

2. **Investigate Unknown Licenses** (Priority: HIGH)
   - Review the 5 packages listed above
   - Add to allowlist once verified

3. **Document License Decision** (Priority: MEDIUM)
   - Create LICENSE-APPROVAL.md documenting approved licenses
   - Add rationale for accepting GPL/LGPL dependencies

### Long-term Improvements

1. **Automate License Checking** in CI/CD:
   ```bash
   pip install pip-licenses
   pip-licenses --fail-on="GPL-3.0;AGPL-3.0"
   ```

2. **Add SBOM Generation** to build pipeline:
   ```bash
   cyclonedx-py environment -o sbom.json
   ```

3. **Regular Scanning** for new dependencies:
   - Run license check on every `pip install`
   - Block PRs introducing non-compliant licenses

4. **Consider Alternatives** for GPL dependencies:
   - PyInstaller -> alternative: `shiv`, `pex`, or `py2exe`
   - chardet -> already LGPL (safe for linking)

---

## Appendix: Full License Inventory

### Complete Package List by License


### MIT

- Faker@40.5.1
- PyYAML@6.0.3
- altgraph@0.17.5
- annotated-doc@0.0.4
- annotated-types@0.7.0
- anyio@4.12.1
- attrs@25.4.0
- beautifulsoup4@4.14.3
- cffi@2.0.0
- cfgv@3.5.0
- charset-normalizer@3.4.4
- colorlog@6.10.1
- docling-core@2.65.2
- docling-ibm-models@3.11.0
- docling-parse@5.4.0
- docling@2.75.0
- dparse@0.6.4
- et_xmlfile@2.0.0
- filelock@3.24.3
- filetype@1.2.0
- h11@0.16.0
- identify@2.6.16
- iniconfig@2.3.0
- interrogate@1.7.0
- jsonref@1.1.0
- jsonschema-specifications@2025.9.1
- jsonschema@4.26.0
- lark@1.3.1
- latex2mathml@3.78.1
- librt@0.8.1
- linkify-it-py@2.1.0
- macholib@1.16.4
- markdown-it-py@4.0.0
- marko@2.2.2
- marshmallow@4.2.2
- mdit-py-plugins@0.5.0
- mdurl@0.1.2
- mpire@2.10.2
- mypy@1.19.1
- mypy_extensions@1.1.0
- ocrmac@1.0.1
- openpyxl@3.1.5
- packageurl-python@0.17.6
- pip-licenses@5.5.1
- pip-requirements-parser@32.0.1
- pip@23.2.1
- platformdirs@4.9.2
- pluggy@1.6.0
- polyfactory@3.3.0
- pre_commit@4.5.1
- py@1.11.0
- pyclipper@1.4.0
- pydantic-settings@2.13.1
- pydantic@2.12.5
- pydantic_core@2.41.5
- pylatexenc@2.10
- pyobjc-core@12.1
- pyobjc-framework-Cocoa@12.1
- pyobjc-framework-CoreML@12.1
- pyobjc-framework-Quartz@12.1
- pyobjc-framework-Vision@12.1
- pyparsing@3.3.2
- pytest-cov@7.0.0
- pytest@9.0.2
- python-discovery@1.0.0
- python-docx@1.2.0
- python-pptx@1.0.2
- pytz@2025.2
- referencing@0.37.0
- rfc3339-validator@0.1.4
- rfc3986-validator@0.1.1
- rfc3987-syntax@1.1.0
- rich@14.3.3
- rpds-py@0.30.0
- rtree@1.4.1
- ruamel.yaml@0.19.1
- ruff@0.15.2
- safety-schemas@0.0.16
- safety@3.7.0
- secondbrain@0.1.0
- semchunk@2.2.2
- setuptools@82.0.0
- six@1.17.0
- soupsieve@2.8.3
- tabulate@0.9.0
- textual@8.0.2
- tomlkit@0.14.0
- tree-sitter-c@0.24.1
- tree-sitter-javascript@0.25.0
- tree-sitter-python@0.25.0
- tree-sitter-typescript@0.23.2
- tree-sitter@0.25.2
- typer@0.21.2
- typing-inspection@0.4.2
- uc-micro-py@2.0.0
- uri-template@1.3.0
- urllib3@2.6.3
- virtualenv@21.0.0
- wcwidth@0.6.0

### BSD-3-Clause

- Authlib@1.6.8
- MarkupSafe@3.0.3
- click@8.3.1
- dill@0.4.1
- fsspec@2026.2.0
- httpcore@1.0.9
- httpx@0.28.1
- idna@3.11
- joblib@1.5.3
- lxml@6.0.2
- multiprocess@0.70.19
- networkx@3.6.1
- prettytable@3.17.0
- psutil@7.2.2
- pycparser@3.0
- python-dotenv@1.2.1
- torch@2.10.0
- webcolors@25.10.0

### Apache-2.0

- bandit@1.9.4
- coverage@7.13.4
- cyclonedx-bom@7.2.2
- cyclonedx-python-lib@11.6.0
- hf-xet@1.3.1
- license-expression@30.4.4
- py-serializable@2.1.0
- pymongo@4.16.0
- pytest-asyncio@1.3.0
- pytest-memray@1.8.0
- rapidocr@3.6.0
- requests@2.32.5
- stevedore@5.7.0
- tzdata@2025.3

### BSD License

- Jinja2@3.1.6
- colorama@0.4.6
- jsonlines@4.0.0
- jsonpointer@3.0.0
- mpmath@1.3.0
- nodeenv@1.10.0
- omegaconf@2.3.0
- pandas@2.3.3
- reportlab@4.4.10
- scipy@1.17.1
- shapely@2.1.2
- sympy@1.14.0

### Apache Software License

- accelerate@1.12.0
- arrow@1.4.0
- huggingface_hub@0.36.2
- memray@1.19.1
- nltk@3.9.3
- opencv-python@4.13.0.92
- python-dateutil@2.9.0.post0
- safetensors@0.7.0
- sortedcontainers@2.4.0
- tenacity@9.1.4
- tokenizers@0.22.2
- transformers@4.57.6

### ISC

- dnspython@2.8.0
- isoduration@20.11.0
- mongomock@4.3.0
- shellingham@1.5.4

### BSD-2-Clause

- Pygments@2.19.2
- boolean.py@5.0
- xlsxwriter@3.2.9

### PSF-2.0

- distlib@0.4.0
- typing_extensions@4.15.0

### declared license of 'antlr4-python3-runtime'

- antlr4-python3-runtime@4.9.3

### Python-2.0

- defusedxml@0.7.1

### MIT-CMU

- pillow@12.1.1

### declared license of 'pypdfium2'

- pypdfium2@5.5.0

### declared license of 'sentinels'

- sentinels@1.1.1

### declared license file: LICENSE

- torchvision@0.25.0

### MPL-2.0 (Weak Copyleft)

- certifi@2026.2.25
- fqdn@1.5.1
- pathspec@1.0.4

### GPL/LGPL (Strong Copyleft)

- chardet@5.2.0
- pyinstaller@6.19.0
- pyinstaller-hooks-contrib@2026.1

### UNKNOWN (Manual Review Required)

- cryptography@46.0.5
- numpy@2.4.2
- packaging@26.0
- regex@2026.2.19
- tqdm@4.67.3

---

*Report generated from CycloneDX SBOM using automated license analysis.*
*Review date: 2026-03-07*
