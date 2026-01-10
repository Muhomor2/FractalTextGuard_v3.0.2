# Limitations and Caveats

## What This Tool Is

FractalTextGuard is a **statistical analysis tool** that calculates structural metrics (Hurst exponent, repetition rates, entropy) from text. It provides signals that may indicate unusual patterns.

## What This Tool Is NOT

- **Not a lie detector**: Cannot determine intent or authorship
- **Not infallible**: False positives and false negatives occur
- **Not forensic evidence**: Results are probabilistic indicators, not proof
- **Not a replacement for human judgment**: Should be one input among many

## Known Limitations

### 1. Text Length Requirements

| Length | Reliability |
|--------|-------------|
| < 200 tokens | Very low (DFA unstable) |
| 200-500 tokens | Low (wide confidence intervals) |
| 500-2000 tokens | Moderate |
| > 2000 tokens | Better (but not guaranteed) |

**Recommendation**: Do not rely on verdicts for texts under 500 tokens.

### 2. Domain Sensitivity

Default thresholds were developed on general English text. Performance may vary on:

- Technical/scientific writing
- Legal documents
- Poetry or creative writing
- Non-English languages
- Code-heavy documents
- Translated text

**Recommendation**: Calibrate thresholds for your specific domain.

### 3. Adversarial Robustness

This tool can be evaded by:

- Adding random variations to AI output
- Post-processing with paraphrasing
- Mixing human and AI content
- Training models to produce lower-H output

**Recommendation**: Do not assume detection is complete or final.

### 4. Base Rate Problem

If AI-generated text is rare in your corpus, even a 95% accurate detector will produce many false positives. Example:

- 1000 documents, 10 are AI-generated
- 95% true positive rate: catches 9.5 AI texts
- 5% false positive rate: flags 49.5 human texts
- Precision: 9.5 / 59 ≈ 16%

**Recommendation**: Consider base rates when interpreting results.

### 5. Temporal Drift

As language models improve, their statistical signatures may change. Thresholds calibrated today may not work tomorrow.

**Recommendation**: Re-calibrate periodically.

## Appropriate Use

✅ **Appropriate:**
- Screening tool to flag documents for human review
- Research on text structure and LRD properties
- Educational demonstration of statistical analysis
- One signal in a multi-factor assessment

❌ **Not appropriate:**
- Sole basis for academic punishment
- Automated rejection without human review
- Legal evidence without corroboration
- High-stakes decisions without calibration

## Disclaimer

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND. The author makes no claims about detection accuracy in any specific use case. Users are responsible for validating results in their context.
