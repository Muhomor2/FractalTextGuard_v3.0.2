# Verdict Policy (HEALTHY / WARNING / CRITICAL)

This release standardizes FractalTextGuard verdicts to **HEALTHY / WARNING / CRITICAL** to match the GSL-LRD security/audit style and simplify cross-tool stress testing.

## 1) Exact mapping (legacy → new)

| Legacy label (<= v3.0.1) | New label (>= v3.0.2) | Meaning |
|---|---|---|
| AUTHENTIC | **HEALTHY** | No strong LRD/repetition signature detected. |
| SUSPICIOUS *(or UNCERTAIN in older drafts)* | **WARNING** | Mixed / ambiguous signals; needs more context or more text. |
| AI_DETECTED | **CRITICAL** | Strong structural signal consistent with generation / templated output / extreme repetition. |

**Backwards compatibility:** JSON output includes both fields:
- `verdict`: **HEALTHY/WARNING/CRITICAL**
- `legacy_verdict`: AUTHENTIC/SUSPICIOUS/AI_DETECTED

## 2) How the verdict is decided (score → label)

The core uses a **weighted “suspiciousness score”** `score ∈ [0,1]` built from several interpretable signals:

- DFA/LRD proxy (Hurst exponent **H** and its stability)
- Repetition (n-gram rates; line repeats)
- Compressibility ratio
- Shannon entropy

### Default decision thresholds

The default rule is:

- **CRITICAL** if `score ≥ 0.55`
- **WARNING** if `0.30 ≤ score < 0.55`
- **HEALTHY** if `score < 0.30`

> Note: these are **tool defaults**, not a universal law of nature. You should calibrate thresholds to your domain using the provided stress-test suite.

## 3) When NOT to use the verdict (industrial limitations)

### Too-short inputs
If the input is very short (few sentences / a couple hundred tokens), DFA/LRD estimates become unstable and confidence bands widen.
- Expect more **WARNING** verdicts.
- Prefer **≥ 1–2k words** for meaningful LRD-based separation.
- For audit workflows: treat short texts as **“insufficient evidence”**.

### Highly non-natural text
Some inputs can look “AI-like” structurally even if they are not:
- logs, code dumps, config files, tables, boilerplate/legal text
- repeated templates (forms, invoices)
- extreme copy/paste

In these cases, use verdict as **structure-risk**, not “authorship proof”.

### Very large files
For multi-megabyte texts, runtime and memory can grow.
Industrial practice:
- sample/chunk (head/stride sampling) and report aggregation
- run with timeouts in batch mode
- set a maximum file size in your pipeline

## 4) Recommended usage patterns

- **Security / bot detection:** prefer **CRITICAL** as a “high-structure risk” flag; follow-up with additional checks.
- **Academic integrity:** use as one signal, not as sole evidence.
- **Document forensics:** use on sufficiently long text; keep the raw metrics with the report for reproducibility.

