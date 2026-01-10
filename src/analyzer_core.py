#!/usr/bin/env python3
"""Core analyzer module - stdlib only, with improved repetition detection"""

from __future__ import annotations
import hashlib, math, re, statistics, zlib
from typing import Dict, List, Optional, Tuple

CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")

THRESHOLDS = {
    "H_suspicious": 0.65, "H_ai_detected": 0.75,
    "H_anti_persistent": 0.40,
    "compress_suspicious": 0.45,
    "repeat_suspicious": 0.15, "repeat_ai": 0.30,
    "trigram_suspicious": 0.15, "trigram_ai": 0.25,
    "fivegram_suspicious": 0.10, "fivegram_ai": 0.18,
    "entropy_low": 3.8,
}

# Verdict mapping (compatibility)
# Legacy labels (<=v3.0.1): AUTHENTIC / SUSPICIOUS / AI_DETECTED  (some drafts used UNCERTAIN)
# New labels (industrial, aligned with GSL-LRD): HEALTHY / WARNING / CRITICAL
LEGACY_TO_HWC = {
    "AUTHENTIC": "HEALTHY",
    "UNCERTAIN": "WARNING",
    "SUSPICIOUS": "WARNING",
    "AI_DETECTED": "CRITICAL",
}
HWC_TO_LEGACY = {"HEALTHY": "AUTHENTIC", "WARNING": "SUSPICIOUS", "CRITICAL": "AI_DETECTED"}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def strip_code_blocks(text: str) -> Tuple[str, Dict]:
    stats = {"fenced_blocks": 0, "inline_spans": 0}
    def repl_fence(m): stats["fenced_blocks"] += 1; return "\n"
    def repl_inline(m): stats["inline_spans"] += 1; return ""
    return INLINE_CODE_RE.sub(repl_inline, CODE_FENCE_RE.sub(repl_fence, text)), stats

def tokenize_simple(text: str) -> List[str]:
    return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)

def shannon_entropy_bytes(b: bytes) -> float:
    if not b: return 0.0
    freq = [0] * 256
    for x in b: freq[x] += 1
    n = len(b)
    return -sum((c/n) * math.log2(c/n) for c in freq if c > 0)

def compressibility_ratio(b: bytes) -> float:
    if not b: return 1.0
    return len(zlib.compress(b, 9)) / len(b)

def repetition_metrics(text: str) -> Dict:
    cleaned, _ = strip_code_blocks(text)
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if not lines: return {"ok": False, "repeat_rate": 0.0, "trigram_repeat_rate": 0.0, "fivegram_repeat_rate": 0.0}
    
    total, unique = len(lines), len(set(lines))
    line_repeat = 1.0 - (unique/total)
    
    tokens = tokenize_simple(cleaned.lower())
    
    trigrams = [" ".join(tokens[i:i+3]) for i in range(len(tokens)-2)] if len(tokens) >= 3 else []
    trigram_repeat = 1.0 - (len(set(trigrams)) / len(trigrams)) if trigrams else 0.0
    
    fivegrams = [" ".join(tokens[i:i+5]) for i in range(len(tokens)-4)] if len(tokens) >= 5 else []
    fivegram_repeat = 1.0 - (len(set(fivegrams)) / len(fivegrams)) if fivegrams else 0.0
    
    phrase_counts = {}
    for i in range(len(tokens) - 4):
        phrase = " ".join(tokens[i:i+5])
        phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
    top_phrases = sorted(phrase_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "ok": True, "lines_total": total, "unique_lines": unique,
        "repeat_rate": line_repeat, "trigram_repeat_rate": trigram_repeat,
        "fivegram_repeat_rate": fivegram_repeat,
        "top_phrases": [(p, c) for p, c in top_phrases if c > 1]
    }

def universal_poly_fit(xv, yv, deg):
    m = deg + 1
    G = [[0.0]*m for _ in range(m)]
    b = [0.0]*m
    for i in range(len(xv)):
        x, y = xv[i], yv[i]
        xp = [1.0]
        for _ in range(deg): xp.append(xp[-1]*x)
        for r in range(m):
            b[r] += y*xp[r]
            for c in range(m): G[r][c] += xp[r]*xp[c]
    A = [G[r]+[b[r]] for r in range(m)]
    for col in range(m):
        piv = col
        for r in range(col+1, m):
            if abs(A[r][col]) > abs(A[piv][col]): piv = r
        if abs(A[piv][col]) < 1e-14: return [0.0]*m
        if piv != col: A[col], A[piv] = A[piv], A[col]
        div = A[col][col]
        for c in range(col, m+1): A[col][c] /= div
        for r in range(m):
            if r == col: continue
            factor = A[r][col]
            for c in range(col, m+1): A[r][c] -= factor*A[col][c]
    return [A[r][m] for r in range(m)]

def poly_eval(coeffs, x):
    acc, xp = 0.0, 1.0
    for c in coeffs: acc += c*xp; xp *= x
    return acc

def dfa_hurst(xs, order=2, n_scales=20):
    n = len(xs)
    if n < 64: return {"ok": False, "H": None}
    mu = statistics.fmean(xs)
    y = []; acc = 0.0
    for v in xs: acc += (v-mu); y.append(acc)
    s_min, s_max = 8, n//4
    if s_max <= s_min: return {"ok": False, "H": None}
    sizes = sorted(set(int(round(s_min*((s_max/s_min)**(i/(n_scales-1))))) for i in range(n_scales)))
    sizes = [s for s in sizes if s >= s_min]
    if len(sizes) < 6: return {"ok": False, "H": None}
    Fs, Ss = [], []
    for s in sizes:
        k = n // s
        if k < 2: continue
        total, count = 0.0, 0
        xv = [float(i) for i in range(s)]
        for w in range(k):
            seg = y[w*s:(w+1)*s]
            coeffs = universal_poly_fit(xv, seg, order)
            ssq = sum((seg[i]-poly_eval(coeffs,float(i)))**2 for i in range(s))
            total += ssq/s; count += 1
        if count == 0: continue
        F = math.sqrt(total/count)
        if F > 0: Fs.append(F); Ss.append(s)
    if len(Fs) < 6: return {"ok": False, "H": None}
    logS = [math.log(float(s)) for s in Ss]
    logF = [math.log(f) for f in Fs]
    mx, my = statistics.fmean(logS), statistics.fmean(logF)
    sxx = sum((x-mx)**2 for x in logS)
    sxy = sum((logS[i]-mx)*(logF[i]-my) for i in range(len(logS)))
    if sxx == 0: return {"ok": False, "H": None}
    H = sxy / sxx
    yhat = [my + H*(logS[i]-mx) for i in range(len(logS))]
    sse = sum((logF[i]-yhat[i])**2 for i in range(len(logF)))
    sst = sum((logF[i]-my)**2 for i in range(len(logF)))
    r2 = 1.0 - (sse/sst) if sst > 0 else 0.0
    return {"ok": True, "H": H, "r2": r2, "n_scales": len(Ss)}

def analyze_text_full(text: str, offline: bool = True) -> Dict:
    b = text.encode("utf-8", errors="replace")
    entropy = shannon_entropy_bytes(b)
    compress = compressibility_ratio(b)
    rep = repetition_metrics(text)
    cleaned, code_stats = strip_code_blocks(text)
    tokens = tokenize_simple(cleaned)
    token_lens = [float(len(t)) for t in tokens if t]
    dfa = dfa_hurst(token_lens, order=2) if len(token_lens) >= 64 else {"ok": False, "H": None}
    
    H = dfa.get("H")
    repeat_rate = rep.get("repeat_rate", 0)
    trigram_repeat = rep.get("trigram_repeat_rate", 0)
    fivegram_repeat = rep.get("fivegram_repeat_rate", 0)
    
    warnings = []
    verdict = "AUTHENTIC"
    confidence = 0.7
    score = 0.0  # Suspiciousness score
    
    # Check H
    if H is not None:
        if H >= THRESHOLDS["H_ai_detected"]:
            score += 0.4
            warnings.append(f"Very high Hurst exponent: {H:.3f}")
        elif H >= THRESHOLDS["H_suspicious"]:
            score += 0.2
            warnings.append(f"Elevated Hurst exponent: {H:.3f}")
        elif H < THRESHOLDS["H_anti_persistent"]:
            score += 0.15
            warnings.append(f"Anti-persistent pattern: {H:.3f}")
    
    # Check compression
    if compress <= THRESHOLDS["compress_suspicious"]:
        score += 0.25
        warnings.append(f"High compressibility: {compress:.3f}")
    
    # Check line repetition
    if repeat_rate >= THRESHOLDS["repeat_ai"]:
        score += 0.35
        warnings.append(f"Very high line repetition: {repeat_rate:.1%}")
    elif repeat_rate >= THRESHOLDS["repeat_suspicious"]:
        score += 0.15
        warnings.append(f"Elevated line repetition: {repeat_rate:.1%}")
    
    # Check n-gram repetition (key for AI detection!)
    if fivegram_repeat >= THRESHOLDS["fivegram_ai"]:
        score += 0.35
        warnings.append(f"High phrase repetition: {fivegram_repeat:.1%}")
    elif fivegram_repeat >= THRESHOLDS["fivegram_suspicious"]:
        score += 0.2
        warnings.append(f"Elevated phrase repetition: {fivegram_repeat:.1%}")
    
    if trigram_repeat >= THRESHOLDS["trigram_ai"]:
        score += 0.25
        warnings.append(f"High trigram repetition: {trigram_repeat:.1%}")
    elif trigram_repeat >= THRESHOLDS["trigram_suspicious"]:
        score += 0.1
        warnings.append(f"Elevated trigram repetition: {trigram_repeat:.1%}")
    
    # Check entropy
    if entropy < THRESHOLDS["entropy_low"]:
        score += 0.15
        warnings.append(f"Low entropy: {entropy:.2f} bits/byte")
    
    # Determine verdict from score
    if score >= 0.55:
        verdict = "AI_DETECTED"
        confidence = min(0.95, 0.7 + score * 0.3)
    elif score >= 0.30:
        verdict = "SUSPICIOUS"
        confidence = min(0.85, 0.65 + score * 0.2)
    else:
        verdict = "AUTHENTIC"
        confidence = max(0.5, 0.8 - score * 0.3)
    
    # Adjustments
    if code_stats.get("fenced_blocks", 0) > 3:
        warnings.append("Code-heavy file: results may be less reliable")
        confidence = max(0.4, confidence - 0.15)
    if len(tokens) < 100:
        warnings.append("Short text: analysis may be less reliable")
        confidence = max(0.35, confidence - 0.2)
    # Map legacy verdict -> HEALTHY/WARNING/CRITICAL (GSL-LRD compatible)
    legacy_verdict = verdict
    verdict = LEGACY_TO_HWC.get(legacy_verdict, "WARNING")

    
    return {
        "verdict": verdict,
        "legacy_verdict": legacy_verdict, "confidence": confidence, "score": round(score, 3),
        "warnings": warnings,
        "metrics": {
            "H": round(H, 4) if H else None,
            "dfa_r2": round(dfa.get("r2", 0), 4) if dfa.get("ok") else None,
            "compress_ratio": round(compress, 4),
            "repeat_rate": round(repeat_rate, 4),
            "trigram_repeat_rate": round(trigram_repeat, 4),
            "fivegram_repeat_rate": round(fivegram_repeat, 4),
            "entropy": round(entropy, 4),
            "tokens": len(tokens), "bytes": len(b)
        },
        "interpretation": {
            "H": _interp_h(H), "compression": _interp_c(compress),
            "repetition": _interp_r(max(repeat_rate, trigram_repeat, fivegram_repeat))
        },
        "top_repeated_phrases": rep.get("top_phrases", [])[:3],
        "code_stats": code_stats, "input_sha256": sha256_hex(b)
    }

def quick_verdict(text: str, offline: bool = True) -> Dict:
    b = text.encode("utf-8", errors="replace")
    compress = compressibility_ratio(b)
    rep = repetition_metrics(text)
    cleaned, _ = strip_code_blocks(text)
    tokens = tokenize_simple(cleaned)
    
    H = None
    if len(tokens) >= 64:
        dfa = dfa_hurst([float(len(t)) for t in tokens if t], order=2, n_scales=12)
        if dfa.get("ok"): H = dfa.get("H")
    
    repeat_rate = rep.get("repeat_rate", 0)
    trigram_repeat = rep.get("trigram_repeat_rate", 0)
    fivegram_repeat = rep.get("fivegram_repeat_rate", 0)
    
    # Quick scoring
    score = 0.0
    if H is not None and H >= 0.65: score += 0.3
    if compress <= 0.45: score += 0.2
    if fivegram_repeat >= 0.15: score += 0.3
    if trigram_repeat >= 0.20: score += 0.2
    if repeat_rate >= 0.20: score += 0.2
    
    if score >= 0.5:
        verdict, confidence = "AI_DETECTED", 0.85
    elif score >= 0.25:
        verdict, confidence = "SUSPICIOUS", 0.75
    else:
        verdict, confidence = "AUTHENTIC", 0.7
    
    warnings = []
    if len(tokens) < 100:
        warnings.append("Short text")
        confidence = max(0.4, confidence - 0.2)
    # Map legacy verdict -> HEALTHY/WARNING/CRITICAL (GSL-LRD compatible)
    legacy_verdict = verdict
    verdict = LEGACY_TO_HWC.get(legacy_verdict, "WARNING")

    
    return {
        "verdict": verdict,
        "legacy_verdict": legacy_verdict, "confidence": confidence, "warnings": warnings,
        "metrics": {"H": round(H, 4) if H else None, "compress_ratio": round(compress, 4),
                    "fivegram_repeat": round(fivegram_repeat, 4)}
    }

def _interp_h(H):
    if H is None: return "N/A (text too short)"
    if H < 0.40: return "Anti-persistent (unusual)"
    if H < 0.55: return "Random-like (human)"
    if H < 0.65: return "Slightly persistent"
    if H < 0.75: return "Persistent (may be AI)"
    return "Highly persistent (AI indicator)"

def _interp_c(r):
    if r > 0.55: return "Normal"
    if r > 0.40: return "Some repetition"
    return "High repetition"

def _interp_r(r):
    if r < 0.10: return "Low (good)"
    if r < 0.20: return "Moderate"
    if r < 0.30: return "Elevated (review)"
    return "High (AI pattern)"
