#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stress_test_rule_based.py (stdlib-only)

Rule-based ensemble scorer for gsl_lrd_universal_analyzer JSON reports.
"""

from __future__ import annotations
import argparse, json, math, os, subprocess, sys, time, hashlib
from typing import Any, Dict, List, Optional, Tuple

SEVERITY = {"HEALTHY": 0, "WARNING": 1, "CRITICAL": 2}
SEVERITY_INV = {v: k for k, v in SEVERITY.items()}

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def clamp01(x: float) -> float:
    if x != x: return 0.0
    return max(0.0, min(1.0, x))

def norm_linear(x: Optional[float], lo: float, hi: float, invert: bool = False) -> float:
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
        return 0.0
    if hi == lo: return 0.0
    v = clamp01((float(x) - lo) / (hi - lo))
    return (1.0 - v) if invert else v

def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("config/labels must be a JSON object")
    return obj

def list_case_files(cases_path: str) -> List[str]:
    if os.path.isfile(cases_path):
        return [cases_path]
    out: List[str] = []
    for root, _, files in os.walk(cases_path):
        for fn in files:
            if fn.startswith("."): continue
            out.append(os.path.join(root, fn))
    out.sort()
    return out

def run_analyzer(analyzer_path, input_path, mode, seed, strict_offline, enable_boxcount, 
                 bc_subsample_method, anchor_iso, cache_key_mode) -> Tuple[bool, Dict, str]:
    cmd = [sys.executable, analyzer_path, "--input", input_path, "--mode", mode, "--seed", str(seed)]
    if strict_offline: cmd.append("--strict-offline")
    if enable_boxcount:
        cmd.append("--enable-boxcount")
        cmd.extend(["--bc-subsample-method", bc_subsample_method])
    if anchor_iso: cmd.extend(["--anchor-iso", anchor_iso])
    if cache_key_mode: cmd.extend(["--cache-key-mode", cache_key_mode])
    
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        out = p.stdout.strip()
        if p.returncode != 0 and not out:
            return False, {}, (p.stderr.strip() or f"nonzero exit code {p.returncode}")
        try:
            obj = json.loads(out)
            return True, obj, (p.stderr.strip() or "")
        except Exception as e:
            return False, {}, f"json_parse_failed: {type(e).__name__}: {e}"
    except Exception as e:
        return False, {}, f"subprocess_failed: {type(e).__name__}: {e}"

def extract_features(report: Dict) -> Dict[str, Optional[float]]:
    feats = {"H": None, "se_H": None, "D_box": None, "compress_ratio": None, "repeat_rate": None, "p_delta": None}
    try:
        atype = report.get("analysis", {}).get("type")
        if atype == "time_series":
            res = report["analysis"]["result"]
            primary = res.get("dfa_primary", {})
            bc = res.get("box_counting_graph", {})
            if isinstance(primary, dict) and primary.get("ok"):
                feats["H"] = float(primary.get("H"))
                feats["se_H"] = float(primary.get("se_H"))
            if isinstance(bc, dict) and bc.get("ok"):
                feats["D_box"] = float(bc.get("D_hat"))
        else:
            res = report["analysis"]["result"]
            feats["compress_ratio"] = float(res.get("compressibility", {}).get("ratio"))
            feats["repeat_rate"] = float(res.get("repetition", {}).get("line_repeat_rate_0_1"))
            lrd = res.get("lrd_proxy", {})
            primary = lrd.get("dfa_tokenlen_primary", {})
            bc = lrd.get("box_counting_graph_tokenlen", {})
            if isinstance(primary, dict) and primary.get("ok"):
                feats["H"] = float(primary.get("H"))
                feats["se_H"] = float(primary.get("se_H"))
            if isinstance(bc, dict) and bc.get("ok"):
                feats["D_box"] = float(bc.get("D_hat"))
        dh = report.get("lrd_memory", {}).get("delta_H_stats", {})
        if isinstance(dh, dict) and dh.get("ok"):
            feats["p_delta"] = float(dh.get("p_value_two_sided"))
    except: pass
    return feats

def score_features(feats: Dict, cfg: Dict) -> Dict:
    weights = cfg.get("weights", {})
    ranges = cfg.get("ranges", {})
    thresholds = cfg.get("thresholds", {"warning": 0.40, "critical": 0.70})
    margin = float(cfg.get("uncertain_margin", 0.05))
    
    def rg(name, default_lo, default_hi):
        r = ranges.get(name, [default_lo, default_hi])
        if not (isinstance(r, list) and len(r) == 2): return default_lo, default_hi
        return float(r[0]), float(r[1])
    
    terms = {}
    
    # H: high persistence -> more suspicious
    H_lo, H_hi = rg("H", 0.45, 0.80)
    terms["H"] = norm_linear(feats.get("H"), H_lo, H_hi, invert=False)
    
    # D_box: for graph of text token lengths, lower D -> more suspicious
    D_lo, D_hi = rg("D_box", 1.0, 2.0)
    terms["D_box"] = norm_linear(feats.get("D_box"), D_lo, D_hi, invert=True)
    
    # repeat_rate: higher -> more suspicious
    rr_lo, rr_hi = rg("repeat_rate", 0.0, 0.40)
    terms["repeat_rate"] = norm_linear(feats.get("repeat_rate"), rr_lo, rr_hi, invert=False)
    
    # compress_ratio: lower (more compressible) -> more suspicious
    cr_lo, cr_hi = rg("compress_ratio", 0.20, 0.95)
    terms["compress_ratio"] = norm_linear(feats.get("compress_ratio"), cr_lo, cr_hi, invert=True)
    
    # p_delta: low p-value (significant change) -> more suspicious
    terms["p_delta"] = norm_linear(feats.get("p_delta"), 0.05, 0.50, invert=True)
    
    ws, vs = [], []
    for name, v in terms.items():
        w = weights.get(name, 1.0)
        if w == 0.0: continue
        ws.append(abs(w))
        vs.append(w * v)
    
    denom = sum(ws) if ws else 1.0
    raw = sum(vs) / denom
    score = clamp01(raw)
    
    warn_thr = float(thresholds.get("warning", 0.40))
    crit_thr = float(thresholds.get("critical", 0.70))
    
    if score >= crit_thr + margin:
        verdict = "CRITICAL"
    elif score >= warn_thr + margin:
        verdict = "WARNING"
    elif score <= warn_thr - margin:
        verdict = "HEALTHY"
    else:
        verdict = "WARNING"
    
    return {"score_0_1": score, "terms": terms, "verdict": verdict, 
            "thresholds": {"warning": warn_thr, "critical": crit_thr}, "uncertain_margin": margin}

def update_confusion(conf, exp, act):
    conf.setdefault(exp, {})
    conf[exp][act] = conf[exp].get(act, 0) + 1

def main() -> int:
    ap = argparse.ArgumentParser(description="Rule-based stress test runner")
    ap.add_argument("--analyzer", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--labels", default=None)
    ap.add_argument("--config", required=True)
    ap.add_argument("--mode", choices=["auto", "text", "ts"], default="auto")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--strict-offline", action="store_true")
    ap.add_argument("--enable-boxcount", action="store_true")
    ap.add_argument("--bc-subsample-method", choices=["random", "stride", "head"], default="stride")
    ap.add_argument("--anchor-iso", default=None)
    ap.add_argument("--cache-key-mode", choices=["digest", "digest+anchor"], default="digest")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-cases", type=int, default=0)
    ap.add_argument("--penalize-upgrades", action="store_true")
    
    args = ap.parse_args()
    cfg = load_json(args.config)
    labels = load_json(args.labels) if args.labels else {}
    files = list_case_files(args.cases)
    if args.max_cases and args.max_cases > 0:
        files = files[:args.max_cases]
    
    t0 = time.time()
    results, failures = [], []
    confusion = {}
    total, passed, fp, fn = 0, 0, 0, 0
    
    for path in files:
        total += 1
        base = os.path.basename(path)
        ok, rep, err = run_analyzer(args.analyzer, path, args.mode, args.seed, 
                                    args.strict_offline, args.enable_boxcount,
                                    args.bc_subsample_method, args.anchor_iso, args.cache_key_mode)
        if not ok:
            failures.append({"file": base, "path": path, "ok": False, "error": err})
            results.append({"file": base, "ok": False, "error": err})
            continue
        
        feats = extract_features(rep)
        scored = score_features(feats, cfg)
        act = scored["verdict"]
        exp = labels.get(base) if isinstance(labels, dict) else None
        if exp not in (None, "HEALTHY", "WARNING", "CRITICAL"): exp = None
        
        item = {"file": base, "features": feats, "score": scored["score_0_1"], 
                "terms": scored["terms"], "verdict": act, "expected": exp}
        results.append(item)
        
        if exp is None:
            passed += 1
            continue
        
        update_confusion(confusion, exp, act)
        exp_s, act_s = SEVERITY[exp], SEVERITY[act]
        
        fail = False
        if act_s < exp_s:
            fail = True
            if exp != "HEALTHY": fn += 1
        elif exp == "HEALTHY" and act != "HEALTHY":
            fail = True
            fp += 1
        elif act_s > exp_s and args.penalize_upgrades:
            fail = True
            if exp == "HEALTHY": fp += 1
        
        if fail:
            failures.append({"file": base, "exp": exp, "act": act, "score": scored["score_0_1"]})
        else:
            passed += 1
    
    dt_ms = int(round((time.time() - t0) * 1000.0))
    
    healthy_total = sum(confusion.get("HEALTHY", {}).values()) if confusion else 0
    summary = {
        "total": total, "passed": passed, "failed": total - passed,
        "pass_rate": (passed / total) if total else 0.0,
        "confusion": confusion, "fp_count": fp, "fn_count": fn,
        "fp_rate_on_healthy": (fp / max(1, healthy_total)) if confusion else None,
        "policy": {"penalize_upgrades": bool(args.penalize_upgrades)}
    }
    
    out = {
        "meta": {"timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "module": os.path.basename(args.analyzer), "seed": args.seed, "duration_ms": dt_ms},
        "summary": summary, "failures_sample": failures[:25], "results_sample": results[:25]
    }
    
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True) if os.path.dirname(args.out) else None
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    
    print(json.dumps({"ok": True, "out": args.out, "summary": summary}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
