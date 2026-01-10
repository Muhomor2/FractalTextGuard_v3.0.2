#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stress_test_hybrid_industrial.py (stdlib-only)
Hybrid scorer with rule-based + ordinal logistic training
"""

from __future__ import annotations
import argparse, concurrent.futures as cf, hashlib, json, math, os, random
import subprocess, sys, time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

CLASSES = ("HEALTHY", "WARNING", "CRITICAL")
SEV = {"HEALTHY": 0, "WARNING": 1, "CRITICAL": 2}
SEV_INV = {0: "HEALTHY", 1: "WARNING", 2: "CRITICAL"}

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def clamp01(x: float) -> float:
    if x != x: return 0.0
    return max(0.0, min(1.0, x))

def safe_float(x) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except: return None

def norm_linear(x: Optional[float], lo: float, hi: float, invert: bool = False) -> float:
    if x is None: return 0.0
    if hi == lo: return 0.0
    v = clamp01((x - lo) / (hi - lo))
    return (1.0 - v) if invert else v

def load_json_obj(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict): raise ValueError(f"{path}: expected JSON object")
    return obj

def list_case_files(cases_path: str) -> List[str]:
    if os.path.isfile(cases_path): return [cases_path]
    out = []
    for root, _, files in os.walk(cases_path):
        for fn in files:
            if not fn.startswith("."): out.append(os.path.join(root, fn))
    out.sort()
    return out

def get_nested(d, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur: return None
        cur = cur[part]
    return cur

@dataclass
class RunArgs:
    analyzer: str; mode: str; seed: int; strict_offline: bool
    enable_boxcount: bool; bc_subsample: str; anchor_iso: Optional[str]
    cache_key_mode: str; timeout_sec: float

def run_analyzer_one(run_args: RunArgs, input_path: str) -> Tuple[str, bool, Dict, str]:
    base = os.path.basename(input_path)
    cmd = [sys.executable, run_args.analyzer, "--input", input_path, "--mode", run_args.mode, "--seed", str(run_args.seed)]
    if run_args.strict_offline: cmd.append("--strict-offline")
    if run_args.enable_boxcount:
        cmd.append("--enable-boxcount")
        cmd.extend(["--bc-subsample-method", run_args.bc_subsample])
    if run_args.anchor_iso: cmd.extend(["--anchor-iso", run_args.anchor_iso])
    if run_args.cache_key_mode: cmd.extend(["--cache-key-mode", run_args.cache_key_mode])
    
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=run_args.timeout_sec)
        payload = (p.stdout or "").strip() or (p.stderr or "").strip()
        if not payload: return base, False, {}, f"empty_output (exit={p.returncode})"
        try:
            obj = json.loads(payload)
            return base, True, obj, (p.stderr or "").strip()
        except Exception as e:
            return base, False, {}, f"json_parse_failed: {type(e).__name__}: {e}"
    except subprocess.TimeoutExpired:
        return base, False, {}, f"timeout>{run_args.timeout_sec}s"
    except Exception as e:
        return base, False, {}, f"subprocess_failed: {type(e).__name__}: {e}"

def extract_base_features(report: Dict) -> Dict[str, Optional[float]]:
    feats = {"H": None, "se_H": None, "D_box": None, "compress_ratio": None, "repeat_rate": None, "p_delta": None}
    try:
        atype = get_nested(report, "analysis.type")
        if atype == "time_series":
            res = get_nested(report, "analysis.result") or {}
            primary = res.get("dfa_primary", {})
            bc = res.get("box_counting_graph", {})
            if isinstance(primary, dict) and primary.get("ok"):
                feats["H"] = safe_float(primary.get("H"))
                feats["se_H"] = safe_float(primary.get("se_H"))
            if isinstance(bc, dict) and bc.get("ok"):
                feats["D_box"] = safe_float(bc.get("D_hat"))
        else:
            res = get_nested(report, "analysis.result") or {}
            feats["compress_ratio"] = safe_float(get_nested(res, "compressibility.ratio"))
            feats["repeat_rate"] = safe_float(get_nested(res, "repetition.line_repeat_rate_0_1"))
            lrd = res.get("lrd_proxy", {})
            primary = lrd.get("dfa_tokenlen_primary", {})
            bc = lrd.get("box_counting_graph_tokenlen", {})
            if isinstance(primary, dict) and primary.get("ok"):
                feats["H"] = safe_float(primary.get("H"))
                feats["se_H"] = safe_float(primary.get("se_H"))
            if isinstance(bc, dict) and bc.get("ok"):
                feats["D_box"] = safe_float(bc.get("D_hat"))
        dh = get_nested(report, "lrd_memory.delta_H_stats")
        if isinstance(dh, dict) and dh.get("ok"):
            feats["p_delta"] = safe_float(dh.get("p_value_two_sided"))
    except: pass
    return feats

def extract_extra_features(report: Dict, extra_cfg: Dict) -> Dict[str, Optional[float]]:
    out = {}
    for name, spec in extra_cfg.items():
        path = spec.get("path", "") if isinstance(spec, dict) else ""
        val = get_nested(report, path) if path else None
        out[name] = safe_float(val)
    return out

def normalize_features(feats_raw: Dict[str, Optional[float]], ranges: Dict, extra_cfg: Dict) -> Dict[str, float]:
    out = {}
    def rg(name): 
        r = ranges.get(name, [0.0, 1.0])
        return (float(r[0]), float(r[1])) if isinstance(r, list) and len(r) == 2 else (0.0, 1.0)
    
    # Base features
    out["H"] = norm_linear(feats_raw.get("H"), *rg("H"), invert=False)
    out["D_box"] = norm_linear(feats_raw.get("D_box"), *rg("D_box"), invert=True)
    out["repeat_rate"] = norm_linear(feats_raw.get("repeat_rate"), *rg("repeat_rate"), invert=False)
    out["compress_ratio"] = norm_linear(feats_raw.get("compress_ratio"), *rg("compress_ratio"), invert=True)
    out["p_delta"] = norm_linear(feats_raw.get("p_delta"), 0.05, 0.50, invert=True)
    
    # Extra features
    for name, spec in extra_cfg.items():
        lo, hi = rg(name)
        inv = spec.get("invert", False) if isinstance(spec, dict) else False
        out[name] = norm_linear(feats_raw.get(name), lo, hi, invert=inv)
    return out

def rule_score(feats_norm: Dict[str, float], weights: Dict) -> Tuple[float, Dict[str, float]]:
    terms = {}
    ws, vs = [], []
    for name, v in feats_norm.items():
        w = weights.get(name, 0.0)
        terms[name] = v
        if w != 0.0:
            ws.append(abs(w))
            vs.append(w * v)
    denom = sum(ws) if ws else 1.0
    score = clamp01(sum(vs) / denom)
    return score, terms

def rule_verdict(score: float, thresholds: Dict, margin: float = 0.05) -> str:
    warn = float(thresholds.get("warning", 0.40))
    crit = float(thresholds.get("critical", 0.70))
    if score >= crit + margin: return "CRITICAL"
    if score >= warn + margin: return "WARNING"
    if score <= warn - margin: return "HEALTHY"
    return "WARNING"

# Ordinal logistic
def sigmoid(x: float) -> float:
    if x > 20: return 1.0
    if x < -20: return 0.0
    return 1.0 / (1.0 + math.exp(-x))

def build_feature_vector(feats_norm: Dict[str, float], order: List[str]) -> List[float]:
    return [feats_norm.get(k, 0.0) for k in order]

def predict_ordinal(w1: List[float], w2: List[float], x: List[float], t_nonhealthy=0.5, t_critical=0.5) -> Tuple[str, Dict]:
    dot1 = sum(w1[i]*x[i] for i in range(len(x)))
    dot2 = sum(w2[i]*x[i] for i in range(len(x)))
    p_nonhealthy = sigmoid(dot1)
    p_critical = sigmoid(dot2)
    if p_critical >= t_critical: v = "CRITICAL"
    elif p_nonhealthy >= t_nonhealthy: v = "WARNING"
    else: v = "HEALTHY"
    return v, {"p_nonhealthy": p_nonhealthy, "p_critical": p_critical}

def train_ordinal(data: List[Tuple[List[float], int]], epochs: int, lr: float, l2: float, seed: int) -> Tuple[List[float], List[float]]:
    if not data: return [], []
    dim = len(data[0][0])
    rng = random.Random(seed)
    w1 = [rng.gauss(0, 0.01) for _ in range(dim)]
    w2 = [rng.gauss(0, 0.01) for _ in range(dim)]
    
    for _ in range(epochs):
        rng.shuffle(data)
        for x, y in data:
            y1 = 1.0 if y >= 1 else 0.0  # WARNING or CRITICAL
            y2 = 1.0 if y >= 2 else 0.0  # CRITICAL
            
            dot1 = sum(w1[i]*x[i] for i in range(dim))
            dot2 = sum(w2[i]*x[i] for i in range(dim))
            p1 = sigmoid(dot1)
            p2 = sigmoid(dot2)
            
            err1 = p1 - y1
            err2 = p2 - y2
            
            for i in range(dim):
                w1[i] -= lr * (err1 * x[i] + l2 * w1[i])
                w2[i] -= lr * (err2 * x[i] + l2 * w2[i])
    return w1, w2

def tune_thresholds(data: List[Tuple[List[float], int]], w1: List[float], w2: List[float]) -> Tuple[float, float]:
    if not data or not w1 or not w2: return 0.5, 0.5
    
    best_t1, best_t2, best_acc = 0.5, 0.5, 0.0
    for t1 in [i*0.05 for i in range(1, 20)]:
        for t2 in [i*0.05 for i in range(1, 20)]:
            correct = 0
            for x, y in data:
                dot1 = sum(w1[i]*x[i] for i in range(len(x)))
                dot2 = sum(w2[i]*x[i] for i in range(len(x)))
                p1 = sigmoid(dot1)
                p2 = sigmoid(dot2)
                if p2 >= t2: pred = 2
                elif p1 >= t1: pred = 1
                else: pred = 0
                if pred == y: correct += 1
            acc = correct / len(data)
            if acc > best_acc:
                best_acc = acc
                best_t1, best_t2 = t1, t2
    return best_t1, best_t2

def eval_fail(exp: str, act: str, tolerate_adjacent_downgrade: bool, penalize_upgrades: bool) -> Tuple[bool, bool, bool]:
    exp_s, act_s = SEV.get(exp, 1), SEV.get(act, 1)
    is_fp, is_fn = False, False
    
    if act_s < exp_s:  # downgrade
        if tolerate_adjacent_downgrade and (exp_s - act_s) == 1:
            return False, False, False
        is_fn = True if exp != "HEALTHY" else False
        return True, is_fp, is_fn
    
    if exp == "HEALTHY" and act != "HEALTHY":
        return True, True, False
    
    if act_s > exp_s and penalize_upgrades:
        is_fp = True if exp == "HEALTHY" else False
        return True, is_fp, False
    
    return False, False, False

def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid industrial stress test")
    ap.add_argument("--analyzer", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--labels", default=None)
    ap.add_argument("--config", required=True)
    ap.add_argument("--use-trained", default=None)
    ap.add_argument("--mode", choices=["auto", "text", "ts"], default="auto")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--strict-offline", action="store_true")
    ap.add_argument("--enable-boxcount", action="store_true")
    ap.add_argument("--bc-subsample-method", choices=["random", "stride", "head"], default="stride")
    ap.add_argument("--anchor-iso", default=None)
    ap.add_argument("--cache-key-mode", choices=["digest", "digest+anchor"], default="digest")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--analyzer-timeout", type=float, default=300.0)
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--train-epochs", type=int, default=40)
    ap.add_argument("--lr", type=float, default=0.2)
    ap.add_argument("--l2", type=float, default=0.001)
    ap.add_argument("--tune-thresholds", action="store_true")
    ap.add_argument("--save-trained", default=None)
    ap.add_argument("--penalize-upgrades", action="store_true")
    ap.add_argument("--tolerate-adjacent-downgrade", action="store_true")
    
    args = ap.parse_args()
    
    cfg = load_json_obj(args.use_trained) if args.use_trained else load_json_obj(args.config)
    labels = load_json_obj(args.labels) if args.labels else {}
    files = list_case_files(args.cases)
    
    weights = cfg.get("weights", {})
    ranges = cfg.get("ranges", {})
    thresholds = cfg.get("thresholds", {"warning": 0.40, "critical": 0.70})
    margin = float(cfg.get("uncertain_margin", 0.05))
    extra_cfg = cfg.get("extra_features", {})
    feature_order = ["H", "D_box", "repeat_rate", "compress_ratio", "p_delta"] + list(extra_cfg.keys())
    
    t0 = time.time()
    run_args = RunArgs(args.analyzer, args.mode, args.seed, args.strict_offline,
                       args.enable_boxcount, args.bc_subsample_method, args.anchor_iso,
                       args.cache_key_mode, args.analyzer_timeout)
    
    # Run analyzer
    items, errors = [], []
    if args.jobs > 1:
        with cf.ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {ex.submit(run_analyzer_one, run_args, f): f for f in files}
            for fut in cf.as_completed(futures):
                base, ok, rep, err = fut.result()
                if ok:
                    items.append({"file": base, "path": futures[fut], "ok": True, "report": rep})
                else:
                    errors.append({"file": base, "error": err})
                    items.append({"file": base, "ok": False, "error": err})
    else:
        for f in files:
            base, ok, rep, err = run_analyzer_one(run_args, f)
            if ok:
                items.append({"file": base, "path": f, "ok": True, "report": rep})
            else:
                errors.append({"file": base, "error": err})
                items.append({"file": base, "ok": False, "error": err})
    
    # Extract features and apply labels
    for it in items:
        if not it.get("ok"): continue
        rep = it.get("report", {})
        base_feats = extract_base_features(rep)
        extra_feats = extract_extra_features(rep, extra_cfg)
        feats_raw = {**base_feats, **extra_feats}
        feats_norm = normalize_features(feats_raw, ranges, extra_cfg)
        
        score, terms = rule_score(feats_norm, weights)
        verdict = rule_verdict(score, thresholds, margin)
        
        it["features_raw"] = feats_raw
        it["features_norm"] = feats_norm
        it["rule"] = {"score": score, "terms": terms, "verdict": verdict}
        it["expected"] = labels.get(it["file"])
        del it["report"]  # Save memory
    
    # Training
    model = None
    if args.train and labels:
        train_data = []
        for it in items:
            if not it.get("ok"): continue
            exp = it.get("expected")
            if exp not in CLASSES: continue
            x = build_feature_vector(it.get("features_norm", {}), feature_order)
            y = SEV[exp]
            train_data.append((x, y))
        
        if train_data:
            w1, w2 = train_ordinal(train_data, args.train_epochs, args.lr, args.l2, args.seed)
            t1, t2 = (0.5, 0.5)
            if args.tune_thresholds:
                t1, t2 = tune_thresholds(train_data, w1, w2)
            
            model = {
                "type": "ordinal_logistic_2stage",
                "w_nonhealthy": w1, "w_critical": w2,
                "t_nonhealthy": t1, "t_critical": t2,
                "feature_order": feature_order
            }
            
            if args.save_trained:
                trained_cfg = {**cfg, "hybrid_model": model}
                with open(args.save_trained, "w", encoding="utf-8") as f:
                    json.dump(trained_cfg, f, ensure_ascii=False, indent=2)
    
    # Load trained model if using
    if args.use_trained and not model:
        hm = cfg.get("hybrid_model")
        if isinstance(hm, dict) and hm.get("type") == "ordinal_logistic_2stage":
            model = hm
            fo = model.get("feature_order")
            if isinstance(fo, list): feature_order = fo
    
    # Apply hybrid predictions
    if model:
        w1 = list(model["w_nonhealthy"])
        w2 = list(model["w_critical"])
        t1 = float(model.get("t_nonhealthy", 0.5))
        t2 = float(model.get("t_critical", 0.5))
        fo = model.get("feature_order", feature_order)
        
        for it in items:
            if not it.get("ok"): continue
            feats_norm = it.get("features_norm", {})
            x = build_feature_vector(feats_norm, fo)
            verdict, probs = predict_ordinal(w1, w2, x, t1, t2)
            it["hybrid"] = {"verdict": verdict, "probs": probs}
    else:
        for it in items:
            if it.get("ok"): it["hybrid"] = None
    
    # Summarize
    def summarize(pred_key: str) -> Dict:
        total, passed, fp, fn = 0, 0, 0, 0
        confusion = {}
        
        for it in items:
            if not it.get("ok"): continue
            total += 1
            exp = it.get("expected")
            act = get_nested(it, f"{pred_key}.verdict") if pred_key == "hybrid" else get_nested(it, "rule.verdict")
            if act not in CLASSES: act = "WARNING"
            
            if exp not in CLASSES:
                passed += 1
                continue
            
            confusion.setdefault(exp, {})
            confusion[exp][act] = confusion[exp].get(act, 0) + 1
            
            bad, isfp, isfn = eval_fail(exp, act, args.tolerate_adjacent_downgrade, args.penalize_upgrades)
            if bad:
                fp += 1 if isfp else 0
                fn += 1 if isfn else 0
            else:
                passed += 1
        
        healthy_total = sum(confusion.get("HEALTHY", {}).values()) if confusion else 0
        return {
            "total": total, "passed": passed, "failed": total - passed,
            "pass_rate": passed / max(1, total),
            "confusion": confusion, "fp_count": fp, "fn_count": fn,
            "fp_rate_on_healthy": fp / max(1, healthy_total) if healthy_total else None
        }
    
    summary_rule = summarize("rule")
    summary_hybrid = summarize("hybrid")
    
    out = {
        "meta": {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "module": os.path.basename(args.analyzer),
            "seed": args.seed, "duration_ms": int((time.time() - t0) * 1000),
            "policy": {"penalize_upgrades": args.penalize_upgrades, "tolerate_adjacent_downgrade": args.tolerate_adjacent_downgrade}
        },
        "summary": {"rule": summary_rule, "hybrid": summary_hybrid, "errors_count": len(errors)},
        "hybrid_model": model,
        "results_sample": items[:25]
    }
    
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    
    print(json.dumps({"ok": True, "out": args.out, "summary": out["summary"]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
