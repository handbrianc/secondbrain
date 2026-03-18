## ADDED Requirements

### Requirement: CycloneDX SBOM generation
The system SHALL support Software Bill of Materials (SBOM) generation using CycloneDX.

#### Scenario: SBOM can be generated
- **WHEN** cyclonedx-bom command is run
- **THEN** SBOM SHALL be generated in JSON format
- **AND** it SHALL include all dependencies

#### Scenario: SBOM is included in pre-commit
- **WHEN** pre-commit runs
- **THEN** cyclonedx-bom hook SHALL generate SBOM
- **AND** SBOM SHALL be compared for unexpected changes

### Requirement: pip-audit vulnerability scanning
The system SHALL support vulnerability scanning using pip-audit.

#### Scenario: Vulnerabilities are detected
- **WHEN** pip-audit is run
- **THEN** known vulnerabilities SHALL be reported
- **AND** affected package versions SHALL be listed

#### Scenario: Scanning is in pre-commit
- **WHEN** pre-commit runs
- **THEN** pip-audit hook SHALL scan dependencies
- **AND** commit SHALL fail if vulnerabilities found

### Requirement: Version bound rationale documentation
Dependency version bounds SHALL be documented with rationale.

#### Scenario: Version ranges are documented
- **WHEN** dependency is pinned (e.g., pymongo>=4.6.0)
- **THEN** rationale SHALL be in requirements.txt comments
- **AND** minimum version reason SHALL be explained

#### Scenario: Major version constraints are explained
- **WHEN** major version is pinned (e.g., >=4.0.0)
- **THEN** breaking changes concern SHALL be documented
- **AND** upgrade path SHALL be noted

### Requirement: Dependency update automation
Dependency updates SHALL be tracked and automated.

#### Scenario: Dependabot configuration exists
- **WHEN** GitHub is used
- **THEN** .github/dependabot.yml SHALL configure updates
- **AND** update frequency SHALL be weekly

#### Scenario: Update PRs are labeled
- **WHEN** dependency update PR is created
- **THEN** it SHALL be labeled "dependencies"
- **AND** it SHALL include changelog link

### Requirement: Security scanning integration
Security scanning SHALL be integrated into CI/CD.

#### Scenario: Bandit security scanning runs
- **WHEN** pre-commit or CI runs
- **THEN** bandit SHALL scan for security issues
- **AND** high-severity issues SHALL block merge

#### Scenario: Safety checks dependencies
- **WHEN** safety check is run
- **THEN** known vulnerabilities SHALL be reported
- **AND** report SHALL include CVE references

### Requirement: Dependency tree visualization
Dependency tree SHALL be visualizable for debugging.

#### Scenario: Dependency tree can be generated
- **WHEN** pipdeptree or similar is run
- **THEN** full dependency tree SHALL be shown
- **AND** conflicts SHALL be highlighted

#### Scenario: Transitive dependencies are visible
- **WHEN** dependency tree is generated
- **THEN** transitive dependencies SHALL be shown
- **AND** depth SHALL be configurable
