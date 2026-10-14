# Third-Party Licenses

Licensing notes for the third-party code SecondBrain installs and ships. SecondBrain itself is
MIT-licensed — see [License](../license.md).

Dependency licenses are read from each installed wheel's `dist-info/METADATA`
(`License-Expression` field); vulnerability auditing is separate (`pip-audit` via
`./scripts/security_scan.sh audit`, SBOM via `./scripts/generate-sbom.sh`). The version/license
pairs below were verified against an installed environment in October 2026 and drift with
dependency upgrades — re-check wheel metadata after bumping dependencies.

## Copyleft dependencies

### fpdf2 — LGPL-3.0-only

`fpdf2` (2.8.9 in `uv.lock`, pinned `>=2.8.9` in `requirements-dev.txt`) is pulled via the
`bundled` extra (`secondbrain[bundled]`) and is licensed `LGPL-3.0-only` (weak copyleft).
It is a development-only dependency in practice: it is used by tests and the `[bundled]`
extra's bundled-PDF tooling, never imported by `src/`.

- **Linking is permitted.** SecondBrain uses fpdf2 as an unmodified library, which the LGPL
  explicitly allows, including in commercial products.
- **Distribution obligations.** If you redistribute SecondBrain with fpdf2 bundled, you must
  pass through fpdf2's LGPL-3.0 license text and copyright, and allow recipients to obtain and
  replace the fpdf2 component under LGPL terms. Pip-based installs already satisfy the
  replacement clause (the original upstream wheel is fetched at install time); Docker images and
  other installers that embed the wheel must keep the license text accessible.
- **No modifications.** SecondBrain pins fpdf2 unmodified from upstream; if you patch it,
  LGPL requires publishing those modifications under the LGPL.
- **Exit ramp.** fpdf2 is only present with the `bundled` extra. If these obligations are
  unacceptable for your packaging, install without that extra.

### MPL-2.0 — file-level copyleft (transitive)

Four installed packages carry `MPL-2.0` (Mozilla Public License 2.0) and one is dual-licensed:

| Package                  | Role                              | License            |
| ------------------------ | --------------------------------- | ------------------ |
| `certifi`                | runtime transitive (CA bundle)    | `MPL-2.0`          |
| `fqdn`                   | runtime transitive (jsonschema)   | `MPL-2.0`          |
| `hypothesis`             | dev/test (property-based testing) | `MPL-2.0`          |
| `pytest-rerunfailures`   | dev/test (pytest plugin)          | `MPL-2.0`          |
| `tqdm`                   | runtime transitive (progress bars)| `MPL-2.0 AND MIT`  |

- **Why this is acceptable.** MPL-2.0 is file-level copyleft: its obligations attach only to
  files of the MPL-licensed work itself. SecondBrain uses all five as unmodified libraries
  (linked or executed), which MPL-2.0 explicitly permits without extending the license to
  larger work — including in commercial products.
- **Obligations.** None for unmodified use. Only if a SecondBrain fork modifies an
  MPL-licensed file must that file (not the surrounding work) be made available under MPL-2.0.
- **tqdm's dual license** offers a permissive choice: the MIT option applies, which carries no
  copyleft obligations at all.

## Proprietary accelerator runtime wheels

`torch` on Linux ships vendor GPU runtime libraries as Python wheels. These are proprietary
redistributables owned by NVIDIA and Intel. SecondBrain code never imports them — they are
native runtime libraries loaded by torch itself. They are downloaded from PyPI or the PyTorch
accelerator indexes at install time; review the vendor terms below before redistributing an
installer that contains them.

### NVIDIA CUDA runtime (transitive via torch)

15 `nvidia-*` wheels are pinned transitively by `torch==2.14.0` (see `requirements.txt` and
`uv.lock`). Licenses from wheel metadata:

| Package                     | Version    | License                        |
| --------------------------- | ---------- | ------------------------------ |
| `nvidia_cublas`             | `13.1.1.3` | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cuda_cupti`         | `13.0.85`  | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cuda_nvrtc`         | `13.0.88`  | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cuda_runtime`       | `13.0.96`  | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cudnn_cu13`         | `9.24.0.43`| `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cufft`              | `12.0.0.61`| `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cufile`             | `1.15.1.6` | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_curand`             | `10.4.0.35`| `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cusolver`           | `12.0.4.66`| `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cusparse`           | `12.6.3.3` | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_cusparselt_cu13`    | `0.8.1`    | NVIDIA Proprietary Software    |
| `nvidia_nccl_cu13`          | `2.30.7`   | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_nvjitlink`          | `13.3.33`  | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_nvshmem_cu13`       | `3.4.5`    | `LicenseRef-NVIDIA-Proprietary`|
| `nvidia_nvtx`               | `13.0.85`  | Apache-2.0                     |

14 of 15 carry NVIDIA proprietary licenses; `nvidia_nvtx` is Apache-2.0. NVIDIA's CUDA EULA
permits redistributing these runtime libraries bundled with an application that requires them,
but prohibits standalone distribution and reverse engineering — review the EULA text shipped in
each wheel's dist-info before packaging installers.

### Intel oneAPI / MKL runtime (XPU builds only)

The XPU torch build used for Intel iGPU/dGPU setups (see
[Document Processing](../getting-started/configuration.md#document-processing)) pulls 8
Intel/MKL wheels. These are **not** pinned in `requirements.txt`/`uv.lock` — they exist only in
environments where torch was installed from the XPU index:

| Package             | Version    | License                            |
| ------------------- | ---------- | ---------------------------------- |
| `intel_cmplr_lib_rt`| `2026.1.0` | Intel EULA for Developer Tools     |
| `intel_cmplr_lib_ur`| `2026.1.0` | Intel EULA for Developer Tools     |
| `intel_cmplr_lic_rt`| `2026.1.0` | Intel EULA for Developer Tools     |
| `intel_opencl_rt`   | `2026.1.0` | Intel EULA for Developer Tools     |
| `intel_openmp`      | `2026.1.0` | Intel EULA for Developer Tools     |
| `intel_sycl_rt`     | `2026.1.0` | Intel EULA for Developer Tools     |
| `mkl`               | `2026.1.0` | Intel Simplified Software License  |
| `intel_pti`         | `1.0.1`    | MIT                                |

Intel developer-tools EULAs are more restrictive than NVIDIA's for redistribution and certain
commercial deployment scenarios — review them before shipping XPU-based images or installers.

## pip-audit blind spot for XPU builds

`torch==2.14.0+xpu`, `torchvision==0.29.0+xpu` and `triton-xpu==3.8.0` come from the PyTorch XPU
index, not PyPI. `pip-audit` matches advisories against PyPI package/version coordinates and
skips these XPU-local builds (they have no PyPI release to match). Compensating controls:

- The PyPI build of the same version is pinned in `requirements.txt` (`torch==2.14.0`), so
  `pip-audit` (via `./scripts/security_scan.sh audit`) still covers the shared torch core;
  advisories against the core generally apply to the XPU build as well.
- The skip is a *matching* limitation, not an all-clear: after bumping the XPU stack, check the
  PyTorch release notes for patched builds and re-run `pip-audit`.
- SBOM generation records the installed `+xpu` versions with their PURLs, so downstream scanners
  that support non-PyPI ecosystems can join advisories themselves.
