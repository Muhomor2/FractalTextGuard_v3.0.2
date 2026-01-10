# Changelog

All notable changes to FractalTextGuard.

## [3.0.2] - 2026-01-10

### Changed
- Standardized verdict labels: HEALTHY / WARNING / CRITICAL
- Added `legacy_verdict` field in JSON for backward compatibility
- Rewrote README with honest limitations and no exaggerated claims
- Added comprehensive LIMITATIONS.md documentation

### Added
- docs/VERDICT_POLICY.md - threshold decision logic
- docs/LIMITATIONS.md - known limitations and appropriate use
- Link to LRD Time Series community on Zenodo

### Fixed
- Updated CITATION.cff with actual DOI (10.5281/zenodo.18202981)

## [3.0.1] - 2026-01-10

### Added
- Industrial stress testing tools
- pyproject.toml for modern packaging
- docs/STRESS_TEST_PROTOCOL.md

## [3.0.0] - 2026-01-09

### Added
- Initial public release
- DFA-based Hurst exponent calculation
- N-gram repetition detection
- Compression ratio and entropy metrics
- CLI for single file and batch processing
- Examples and test suite
