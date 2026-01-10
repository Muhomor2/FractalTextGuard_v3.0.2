# FractalTextGuard

**Structural Text Analysis via Long-Range Dependence Metrics**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![No Dependencies](https://img.shields.io/badge/dependencies-none-green.svg)](requirements.txt)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18202981.svg)](https://doi.org/10.5281/zenodo.18202981)

## Overview

FractalTextGuard analyzes text structure using **Detrended Fluctuation Analysis (DFA)** and related metrics. It calculates the Hurst exponent (H) and other statistical properties that characterize long-range correlations in sequential data.

**What this tool does:**
- Calculates Hurst exponent via DFA (orders 2-4)
- Measures n-gram repetition rates
- Computes compression ratio and Shannon entropy
- Provides structured verdicts: HEALTHY / WARNING / CRITICAL

**What this tool does NOT guarantee:**
- 100% accurate AI detection (no tool can)
- Works equally well on all text types
- Replaces human judgment

> ⚠️ **Important**: This is a statistical analysis tool. Results should be interpreted as one signal among many, not as definitive proof.

---

## Installation

```bash
git clone https://github.com/IgorChechelnitsky/FractalTextGuard.git
cd FractalTextGuard
# Python 3.8+ required. No external dependencies.
```

---

## Usage

```bash
# Single file analysis
python analyze.py --file document.txt

# Batch processing
python analyze.py --folder documents/ --output results.json

# Detailed metrics
python analyze.py --file document.txt --detailed
```

---

## Output

### Verdicts

| Verdict | Meaning |
|---------|---------|
| **HEALTHY** | No strong structural anomalies detected |
| **WARNING** | Mixed signals; manual review recommended |
| **CRITICAL** | Strong structural anomalies (high repetition, abnormal H) |

### Metrics Provided

| Metric | Description | Typical Range |
|--------|-------------|---------------|
| H (Hurst exponent) | Long-range correlation measure | 0.3 - 0.8 |
| Compression ratio | zlib compressibility | 0.3 - 0.7 |
| Trigram repeat rate | 3-gram repetition | 0.05 - 0.30 |
| 5-gram repeat rate | 5-gram repetition | 0.02 - 0.20 |
| Entropy | Shannon entropy (bits/byte) | 3.5 - 5.0 |

---

## Limitations

**Read before use:** See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) and [docs/VERDICT_POLICY.md](docs/VERDICT_POLICY.md)

- **Short texts** (< 500 tokens): DFA estimates become unstable
- **Code-heavy files**: May trigger false positives
- **Domain-specific text**: Thresholds may need calibration
- **Adversarial evasion**: Sophisticated attacks can bypass detection
- **No ground truth**: Verdicts are probabilistic, not deterministic

---

## Calibration

Default thresholds are based on limited testing. For production use:

1. Run stress tests on your domain data:
   ```bash
   python stress_test_rule_based.py --cases your_data/ --labels labels.json
   ```

2. Adjust thresholds in `config.json` based on results

3. Document your calibration methodology

---

## Package Structure

```
FractalTextGuard/
├── analyze.py              # CLI entry point
├── src/
│   ├── analyzer_core.py    # Core DFA/metrics
│   └── gsl_lrd_v25.py      # Extended analyzer
├── docs/
│   ├── LIMITATIONS.md
│   └── VERDICT_POLICY.md
├── examples/               # Test files
├── tests/                  # Unit tests
├── stress_test_*.py        # Calibration tools
├── config.json             # Thresholds
├── LICENSE                 # CC BY-NC 4.0
└── CITATION.cff
```

---

## Related Work

This tool is part of the **LRD Time Series Analysis** research community:
- Community: https://zenodo.org/communities/lrd-time-series/records
- Related publications: See CITATION.cff

---

## License

**Non-Commercial Use**

| Use | Status |
|-----|--------|
| Personal / Academic / Educational | ✅ Free |
| Commercial | ❌ Requires written permission |

See [LICENSE](LICENSE) for full terms.

---

## Citation

```bibtex
@software{chechelnitsky2026fractaltextguard,
  author = {Chechelnitsky, Igor},
  title = {FractalTextGuard: Structural Text Analysis via Long-Range Dependence},
  year = {2026},
  publisher = {Zenodo},
  version = {3.0.2},
  doi = {10.5281/zenodo.18202981},
  url = {https://github.com/IgorChechelnitsky/FractalTextGuard}
}
```

---

## Author

**Igor Chechelnitsky**  
ORCID: [0009-0007-4607-1946](https://orcid.org/0009-0007-4607-1946)

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

**v3.0.2**: Standardized verdicts (HEALTHY/WARNING/CRITICAL), added limitations docs.
