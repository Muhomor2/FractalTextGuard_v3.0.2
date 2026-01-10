# Zenodo Upload Information

## For: https://zenodo.org/records/18202981

---

## Title
```
FractalTextGuard: Structural Text Analysis via Long-Range Dependence
```

## Version
```
3.0.2
```

## Description (Copy this to Zenodo)
```
FractalTextGuard is a Python toolkit for structural text analysis using Detrended Fluctuation Analysis (DFA) and Long-Range Dependence (LRD) metrics.

Features:
• Hurst exponent (H) calculation via DFA (orders 2-4)
• N-gram repetition rate detection (trigrams, 5-grams)
• Compression ratio analysis
• Shannon entropy calculation
• Configurable verdicts: HEALTHY / WARNING / CRITICAL
• Batch processing for multiple files
• Stress-testing tools for threshold calibration

Technical specifications:
• Python 3.8+ required
• Zero external dependencies (stdlib only)
• Fully offline operation
• JSON output with legacy compatibility

IMPORTANT: This is a statistical analysis tool. Results are probabilistic indicators, not definitive proof. See LIMITATIONS.md for known constraints and appropriate use cases.

Part of the LRD Time Series Analysis research community.
```

## Keywords (for Zenodo)
```
text analysis, Hurst exponent, DFA, detrended fluctuation analysis, long-range dependence, LRD, structural analysis, statistical analysis, Python
```

## License
```
Creative Commons Attribution Non Commercial 4.0 International (CC-BY-NC-4.0)
```

## Communities
```
lrd-time-series
```

## Related identifiers
```
GitHub: https://github.com/IgorChechelnitsky/FractalTextGuard (isSupplementTo)
Community: https://zenodo.org/communities/lrd-time-series/records (isPartOf)
```

## Authors
```
Chechelnitsky, Igor
ORCID: 0009-0007-4607-1946
Affiliation: Independent Researcher
```

---

## Files to Upload

1. FractalTextGuard_v3.0.2.zip (main package)
2. README.md
3. LICENSE

---

## Release Notes (for Zenodo)
```
v3.0.2 - Honest Industrial Release

Changes:
- Standardized verdicts: HEALTHY / WARNING / CRITICAL
- Added comprehensive LIMITATIONS.md (known constraints, appropriate use)
- Rewrote documentation without exaggerated claims
- Added link to LRD Time Series community
- Backward compatibility via legacy_verdict field

This release prioritizes honest documentation over marketing claims.
```
