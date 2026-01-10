#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gsl_lrd_universal_analyzer_v2.5 - CLI compatible version"""

from __future__ import annotations
import argparse, datetime as _dt, hashlib, json, math, os, platform, random
import re, statistics, sys, tempfile, zlib

try:
    from zoneinfo import ZoneInfo
except: ZoneInfo = None

TZ_NAME = "Asia/Jerusalem"
SOLSTICE_DATE = (2026, 6, 21, 0, 0, 0)

def now_local():
    if ZoneInfo:
        try: return _dt.datetime.now(ZoneInfo(TZ_NAME))
        except: pass
    return _dt.datetime.now()

def solstice_local():
    y,m,d,hh,mm,ss = SOLSTICE_DATE
    if ZoneInfo:
        try: return _dt.datetime(y,m,d,hh,mm,ss,tzinfo=ZoneInfo(TZ_NAME))
        except: pass
    return _dt.datetime(y,m,d,hh,mm,ss)

def minutes_to_solstice(ts=None):
    ts = ts or now_local()
    target = solstice_local()
    if (ts.tzinfo is None) != (target.tzinfo is None):
        ts = ts.replace(tzinfo=None)
        target = target.replace(tzinfo=None)
    return int((target - ts).total_seconds() // 60)

def build_solstice_anchor(input_digest_hex, ts=None):
    ts = ts or now_local()
    ts_iso = ts.isoformat()
    m2s = minutes_to_solstice(ts)
    anchor_payload = f"{ts_iso}|m2s={m2s}|in={input_digest_hex}"
    return {"timestamp_iso":ts_iso,"timezone":TZ_NAME,"minutes_to_solstice":m2s,
            "anchor_sha256":hashlib.sha256(anchor_payload.encode()).hexdigest()}

NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")

def sha256_hex(data): return hashlib.sha256(data).hexdigest()
def safe_decode(b):
    try: return b.decode("utf-8")
    except: return b.decode("latin-1", errors="replace")
def read_bytes(path):
    with open(path, "rb") as f: return f.read()

def median(xs): return statistics.median(xs) if xs else float("nan")

def summarize_series(xs):
    if not xs: return {"n":0}
    n = len(xs)
    return {"n":n,"mean":statistics.fmean(xs),"std_pop":statistics.pstdev(xs) if n>=2 else 0.0,
            "min":min(xs),"max":max(xs),"median":median(xs)}

def _next_pow2(n):
    p = 1
    while p < n: p <<= 1
    return p

def fft_inplace(a):
    n = len(a)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit: j ^= bit; bit >>= 1
        j ^= bit
        if i < j: a[i], a[j] = a[j], a[i]
    length = 2
    while length <= n:
        ang = -2.0 * math.pi / length
        wlen = complex(math.cos(ang), math.sin(ang))
        for i in range(0, n, length):
            w = 1.0 + 0.0j
            half = length // 2
            for jj in range(i, i + half):
                u, v = a[jj], a[jj + half] * w
                a[jj], a[jj + half] = u + v, u - v
                w *= wlen
        length <<= 1
    return a

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
            if factor == 0.0: continue
            for c in range(col, m+1): A[r][c] -= factor*A[col][c]
    return [A[r][m] for r in range(m)]

def poly_eval(coeffs, x):
    acc, xp = 0.0, 1.0
    for c in coeffs: acc += c*xp; xp *= x
    return acc

_TCRIT = {1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262,10:2.228}
def tcrit_975(df): return _TCRIT.get(df, 1.96) if df > 0 else 1.96

def linreg_with_se(x, y):
    n = len(x)
    if n < 3: return {"ok":False}
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((x[i]-mx)**2 for i in range(n))
    if sxx == 0: return {"ok":False}
    sxy = sum((x[i]-mx)*(y[i]-my) for i in range(n))
    slope = sxy/sxx
    intercept = my - slope*mx
    yhat = [intercept + slope*x[i] for i in range(n)]
    sse = sum((y[i]-yhat[i])**2 for i in range(n))
    sst = sum((y[i]-my)**2 for i in range(n))
    r2 = 1.0 - (sse/sst) if sst > 0 else 0
    df = n - 2
    se_slope = math.sqrt((sse/df)/sxx) if df > 0 and (sse/df)/sxx > 0 else 0.0
    return {"ok":True,"slope":slope,"se_slope":se_slope,"r2":r2,"df":df}

def dfa_hurst(xs, order=2, n_scales=20):
    n = len(xs)
    if n < 64: return {"ok":False,"reason":"n<64"}
    mu = statistics.fmean(xs)
    y = []; acc = 0.0
    for v in xs: acc += (v - mu); y.append(acc)
    s_min, s_max = 8, n//4
    if s_max <= s_min: return {"ok":False,"reason":"n too small"}
    sizes = sorted(set(int(round(s_min*((s_max/s_min)**(i/(max(8,n_scales)-1))))) for i in range(max(8,n_scales))))
    sizes = [s for s in sizes if s >= s_min]
    if len(sizes) < 6: return {"ok":False,"reason":"insufficient scales"}
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
    if len(Fs) < 6: return {"ok":False,"reason":"insufficient valid scales"}
    logS = [math.log(float(s)) for s in Ss]
    logF = [math.log(f) for f in Fs]
    reg = linreg_with_se(logS, logF)
    if not reg.get("ok"): return {"ok":False}
    H = float(reg["slope"])
    se_H = float(reg["se_slope"])
    df = int(reg["df"])
    tcrit = tcrit_975(df)
    return {"ok":True,"H":H,"se_H":se_H,"ci95_H":[H-tcrit*se_H,H+tcrit*se_H],"order":order,
            "r2":float(reg["r2"]),"df":df,"confidence_0_1":min(1.0,0.3+0.1*len(Ss))}

def _subsample_indices(n0, k, method, seed):
    if k >= n0: return list(range(n0))
    if method == "head": return list(range(k))
    if method == "stride":
        if k <= 1: return [0]
        step = (n0-1)/(k-1)
        return sorted(set(max(0,min(n0-1,int(round(i*step)))) for i in range(k)))[:k]
    rng = random.Random(seed)
    return sorted(rng.sample(range(n0), k=k))

def box_counting(ys, n_scales=9, eps_min_pow2=8, eps_max_pow2=2, max_n=20000, seed=12345, method="stride"):
    n0 = len(ys)
    if n0 < 32: return {"ok":False,"reason":"n<32"}
    if max_n > 0 and n0 > max_n:
        idx = _subsample_indices(n0, max_n, method, seed)
        ys2 = [ys[i] for i in idx]; n = len(ys2)
    else: ys2, n = list(ys), n0
    y_min, y_max = min(ys2), max(ys2)
    if y_max == y_min: return {"ok":False,"reason":"constant"}
    eps_pows = list(range(eps_max_pow2, eps_min_pow2+1))
    eps_list = [2.0**(-p) for p in eps_pows]
    Ns = []
    for eps in eps_list:
        boxes = set()
        for i, yv in enumerate(ys2):
            x = i/(n-1) if n > 1 else 0.0
            y = (yv-y_min)/(y_max-y_min)
            boxes.add((int(x/eps), int(y/eps)))
        Ns.append(len(boxes))
    valid = [i for i in range(len(Ns)) if Ns[i] < 0.9*n]
    if len(valid) < 4: return {"ok":False,"reason":"saturation"}
    xreg = [math.log(1.0/eps_list[i]) for i in valid]
    yreg = [math.log(float(Ns[i])) for i in valid]
    reg = linreg_with_se(xreg, yreg)
    if not reg.get("ok"): return {"ok":False}
    return {"ok":True,"D_hat":float(reg["slope"]),"r2":float(reg["r2"]),"n_used":n}

def strip_code_blocks(text):
    stats = {"fenced_blocks":0,"inline_code_spans":0}
    def repl_fence(m): stats["fenced_blocks"] += 1; return "\n<CODE_BLOCK>\n"
    def repl_inline(m): stats["inline_code_spans"] += 1; return "<INLINE_CODE>"
    t1 = CODE_FENCE_RE.sub(repl_fence, text)
    t2 = INLINE_CODE_RE.sub(repl_inline, t1)
    return t2, stats

def shannon_entropy_bytes(b):
    if not b: return 0.0
    freq = [0]*256
    for x in b: freq[x] += 1
    n = len(b)
    return -sum((c/n)*math.log2(c/n) for c in freq if c)

def compressibility_ratio(b, level=9):
    if not b: return {"ratio":1.0,"compressed_len":0,"orig_len":0}
    comp = zlib.compress(b, level)
    return {"ratio":len(comp)/len(b) if b else 1.0,"compressed_len":len(comp),"orig_len":len(b)}

def tokenize_simple(text): return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)

def repetition_metrics(text):
    cleaned, gate_stats = strip_code_blocks(text)
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if not lines: return {"ok":False,"reason":"empty","anti_fp_gate":gate_stats}
    total = len(lines)
    counts = {}
    for ln in lines: counts[ln] = counts.get(ln,0)+1
    most_common_line, most_common_count = max(counts.items(), key=lambda kv:kv[1])
    repeat_rate = 1.0 - (len(counts)/total)
    return {"ok":True,"anti_fp_gate":gate_stats,"lines_total":total,"unique_lines":len(counts),
            "line_repeat_rate_0_1":repeat_rate,"most_common_line_count":most_common_count}

def tokenlen_series(text):
    cleaned, gate_stats = strip_code_blocks(text)
    toks = tokenize_simple(cleaned)
    lens = [float(len(t)) for t in toks if t and t not in ("<CODE_BLOCK>","<INLINE_CODE>")]
    return lens, gate_stats

def detect_mode(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:50]
    if not lines: return "text"
    numeric_counts = sum(1 for ln in lines for t in re.split(r"[,\s;\t]+", ln) if t and NUM_RE.fullmatch(t))
    token_counts = sum(len(re.split(r"[,\s;\t]+", ln)) for ln in lines)
    if token_counts == 0: return "text"
    return "ts" if numeric_counts / token_counts >= 0.75 else "text"

def parse_ts(text, col=0, delim=None):
    xs = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln: continue
        parts = ln.split(delim) if delim else re.split(r"[,\s;\t]+", ln)
        parts = [p for p in parts if p]
        if 0 <= col < len(parts) and NUM_RE.fullmatch(parts[col]):
            xs.append(float(parts[col]))
    return xs

def env_metadata():
    return {"python":sys.version.replace("\n"," "),"platform":platform.platform()}

DEFAULT_CACHE = os.path.join(os.path.expanduser("~"), ".gsl_lrd_cache.json")

def load_cache(path):
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {"version":1,"items":{}}

def save_cache(path, cache):
    try:
        target = os.path.abspath(os.path.expanduser(path))
        d = os.path.dirname(target)
        if d: os.makedirs(d, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except: pass

def cache_get(cache, key): return cache.get("items",{}).get(key)
def cache_put(cache, key, val): cache.setdefault("items",{})[key] = val

def analyze_ts(xs, args):
    base = summarize_series(xs)
    if base.get("n",0) == 0: return {"ok":False,"reason":"empty series"}
    dfa_all = {}
    for order in args.dfa_orders:
        dfa_all[str(order)] = dfa_hurst(xs, order=order, n_scales=args.dfa_scales)
    primary = dfa_all.get(str(args.dfa_primary), {"ok":False})
    bc = box_counting(xs, max_n=args.bc_max_n, seed=args.seed, method=args.bc_subsample_method) if args.enable_boxcount else None
    return {"ok":True,"summary":base,"dfa_all":dfa_all,"dfa_primary_order":args.dfa_primary,
            "dfa_primary":primary,"box_counting_graph":bc}

def analyze_text(text, args):
    b = text.encode("utf-8", errors="replace")
    ent = shannon_entropy_bytes(b)
    comp = compressibility_ratio(b)
    rep = repetition_metrics(text)
    lens, gate_stats = tokenlen_series(text)
    series_summary = summarize_series(lens)
    dfa_all = {}
    for order in args.dfa_orders:
        dfa_all[str(order)] = dfa_hurst(lens, order=order, n_scales=args.dfa_scales)
    primary = dfa_all.get(str(args.dfa_primary), {"ok":False})
    bc = box_counting(lens, max_n=args.bc_max_n, seed=args.seed, method=args.bc_subsample_method) if args.enable_boxcount else None
    return {"ok":True,"bytes":len(b),"chars":len(text),"entropy_bits_per_byte":ent,
            "compressibility":comp,"repetition":rep,
            "lrd_proxy":{"ok":True,"tokens":len(lens),"anti_fp_gate":gate_stats,
                         "tokenlen_series_summary":series_summary,"dfa_tokenlen_all":dfa_all,
                         "dfa_primary_order":args.dfa_primary,"dfa_tokenlen_primary":primary,
                         "box_counting_graph_tokenlen":bc}}

def build_report(args):
    raw = read_bytes(args.input)
    digest = sha256_hex(raw)
    text = safe_decode(raw)
    mode = args.mode if args.mode != "auto" else detect_mode(text)
    anchor = build_solstice_anchor(digest)
    cache_key = hashlib.sha256((digest + "|" + anchor["anchor_sha256"]).encode()).hexdigest() if args.cache_key_mode == "digest+anchor" else digest
    
    report = {"tool":{"name":"gsl_lrd_universal_analyzer","version":"2.5-golden-master"},
              "input":{"path":args.input,"sha256":digest,"bytes":len(raw),"mode":mode},
              "solstice_anchor":anchor,"cache_key":cache_key,"environment":env_metadata(),
              "analysis":{},"lrd_memory":{},"self_review":{"warnings":[]}}
    
    if mode == "ts":
        xs = parse_ts(text, col=args.col, delim=args.delimiter)
        report["analysis"] = {"type":"time_series","col":args.col,"n_parsed":len(xs),"result":analyze_ts(xs,args)}
    else:
        report["analysis"] = {"type":"text","result":analyze_text(text,args)}
    
    report["analysis_sha256"] = sha256_hex(json.dumps(report["analysis"],ensure_ascii=False,sort_keys=True).encode())
    
    # Cache handling
    cache = load_cache(args.cache)
    prev = cache_get(cache, cache_key)
    mem = {"cache_path":args.cache,"found_previous":prev is not None}
    if prev: mem["previous"] = prev
    
    # Store current
    store = {"timestamp_iso":anchor["timestamp_iso"],"input_sha256":digest}
    if report["analysis"]["type"] == "time_series":
        p = report["analysis"]["result"].get("dfa_primary",{})
        bc = report["analysis"]["result"].get("box_counting_graph",{})
    else:
        p = report["analysis"]["result"]["lrd_proxy"].get("dfa_tokenlen_primary",{})
        bc = report["analysis"]["result"]["lrd_proxy"].get("box_counting_graph_tokenlen",{})
    if p.get("ok"):
        store["H"] = float(p.get("H"))
        store["se_H"] = float(p.get("se_H",0))
        store["dfa_order"] = int(p.get("order",args.dfa_primary))
    if bc and bc.get("ok"):
        store["D_box"] = float(bc.get("D_hat"))
    
    cache_put(cache, cache_key, store)
    save_cache(args.cache, cache)
    mem["stored_current"] = store
    
    # Delta-H
    if prev and all(k in prev for k in ("H","se_H","dfa_order")) and all(k in store for k in ("H","se_H","dfa_order")):
        if prev["dfa_order"] == store["dfa_order"]:
            dH = store["H"] - prev["H"]
            se = math.sqrt(prev["se_H"]**2 + store["se_H"]**2)
            z = dH/se if se > 0 else 0
            p_val = math.erfc(abs(z)/math.sqrt(2.0))
            mem["delta_H_stats"] = {"ok":True,"delta_H":dH,"z":z,"p_value_two_sided":p_val}
        else:
            mem["delta_H_stats"] = {"ok":False,"reason":"dfa_order_mismatch"}
    else:
        mem["delta_H_stats"] = {"ok":False,"reason":"missing_fields"}
    
    report["lrd_memory"] = mem
    report["report_sha256"] = sha256_hex(json.dumps(report,ensure_ascii=False,sort_keys=True).encode())
    return report

def _parse_orders(s):
    return sorted(set(int(x.strip()) for x in s.split(",") if x.strip().isdigit()))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True)
    ap.add_argument("--mode", choices=["auto","ts","text"], default="auto")
    ap.add_argument("--col", type=int, default=0)
    ap.add_argument("--delimiter", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--cache-key-mode", choices=["digest","digest+anchor"], default="digest+anchor")
    ap.add_argument("--strict-offline", action="store_true")
    ap.add_argument("--dfa-orders", default="2,3,4")
    ap.add_argument("--dfa-primary", type=int, default=4)
    ap.add_argument("--dfa-scales", type=int, default=20)
    ap.add_argument("--enable-boxcount", action="store_true")
    ap.add_argument("--bc-max-n", type=int, default=20000)
    ap.add_argument("--bc-subsample-method", choices=["random","stride","head"], default="stride")
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--anchor-iso", default=None)
    args = ap.parse_args()
    
    args.dfa_orders = _parse_orders(args.dfa_orders)
    if args.dfa_primary not in args.dfa_orders:
        args.dfa_orders = sorted(set(args.dfa_orders + [args.dfa_primary]))
    
    if not os.path.exists(args.input):
        print(json.dumps({"ok":False,"error":"input_not_found","path":args.input}))
        return 2
    
    report = build_report(args)
    
    if args.out:
        try:
            d = os.path.dirname(os.path.abspath(args.out))
            if d: os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2 if args.pretty else None)
        except Exception as e:
            report["self_review"]["warnings"].append(f"write failed: {e}")
    
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
