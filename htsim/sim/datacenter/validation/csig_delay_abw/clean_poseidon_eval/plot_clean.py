#!/usr/bin/env python3
"""Submission-quality Poseidon-style figures for CSIG/NSCC/HPCC.

Reads raw traces from `validation/csig_delay_abw/poseidon_style/raw/` and
produces:
  - figs/fig14_multihop.{png,pdf}     Multi-hop M/N congestion (a/b/c)
  - figs/fig21a_ablation.{png,pdf}    Signal vs controller ablation
  - figs/fig17_concurrency.{png,pdf}  Stability under high concurrency

HPCC is run with `-q 36` (324 KB queue) to match UEC's auto-sized
queue (327,850 B). This eliminates the ~300k lossless-overflow events
seen with the default 135 KB queue and makes HPCC apples-to-apples on
queue capacity. See notes.md for the full configuration table.
"""

import math
import os
import re
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import json

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.normpath(os.path.join(HERE, "..", "poseidon_style", "raw"))
FIGS_DIR = os.path.join(HERE, "figs")
os.makedirs(FIGS_DIR, exist_ok=True)

LINK_GBPS = 200.0

# Main NSCC/CSIG comparison. HPCC is plotted on a separate reference
# figure (fig14_hpcc_reference) because, even with matched queue size,
# it differs in binary, controller semantics, startup behaviour, and
# ACKNO-based throughput parsing. It is not part of the ablation claim.
MAIN_MODES     = ("baseline_rtt", "csig_poseidon_rate", "csig_delay_abw")
ABLATION_MODES = ("baseline_rtt", "csig_poseidon_rate", "csig_delay_abw")

# Submission-quality labels: short, neutral, no editorial tags.
LABEL = {
    "baseline_rtt":         "NSCC-RTT",
    "csig_poseidon_rate":   "CSIG-Poseidon",
    "csig_delay_abw":            "CSIG delay+ABW",
    "hpcc":                 "HPCC",
}
COLOR = {
    "baseline_rtt":         "#4D4D4D",
    "csig_poseidon_rate":   "#009E73",
    "csig_delay_abw":            "#CC79A7",
    "hpcc":                 "#E69F00",
}
# Distinct line style for HPCC so it's identifiable in BW-print, but
# *not* labeled differently from the rest.
LINESTYLE = {
    "baseline_rtt":         "-",
    "csig_poseidon_rate":   "-",
    "csig_delay_abw":            "-",
    "hpcc":                 (0, (4, 1.5)),
}

# Filename suffix for HPCC runs that use the matched queue size.
HPCC_SUFFIX = "_q36"

# Same staging as run_paper_exact.py so the top axis labels (M,N) line up.
MN_STAGES = [(0, 2, 0), (2, 2, 100000), (2, 9, 200000),
             (9, 9, 300000), (9, 19, 400000)]
MN_END_US = 500000
HC_STAGES = [(50, 0), (100, 25000), (150, 50000), (200, 75000)]

plt.rcParams.update({
    "font.family": "DejaVu Serif",
    "font.size": 10,
    "axes.titlesize": 10,
    "axes.labelsize": 10,
    "axes.titleweight": "bold",
    "legend.fontsize": 8,
    "legend.frameon": True,
    "legend.framealpha": 0.92,
    "legend.edgecolor": "0.7",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.linestyle": ":",
    "grid.linewidth": 0.6,
    "grid.alpha": 0.5,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "figure.dpi": 150,
    "savefig.dpi": 320,
    "savefig.bbox": "tight",
})

TRACE_RE = re.compile(r"^CSIG_TRACE\s+(.+)$")
SW_RE    = re.compile(r"^CSIG_SWITCH\s+(.+)$")
HPCC_RE  = re.compile(
    r"^CWND\d*\s+\d+\s+ACKNO\s+(\d+)\s+at\s+([0-9.]+)\s+src\s+HPCCsrc\s+(\d+)")


def fval(s, default=0.0):
    try: return float(s)
    except Exception: return default


def kv_parse(text):
    return {k: v for k, v in (tok.split("=", 1) for tok in text.split() if "=" in tok)}


def trace_path(scenario, mode):
    if mode == "hpcc":
        # Use the matched-queue HPCC run if present, else fall back to
        # default-queue run. Either way the parser is the same.
        cand = os.path.join(RAW_DIR, "%s__hpcc%s.out" % (scenario, HPCC_SUFFIX))
        if os.path.exists(cand): return cand
        return os.path.join(RAW_DIR, "%s__hpcc.out" % scenario)
    return os.path.join(RAW_DIR, "%s__%s.trace.out" % (scenario, mode))


def read_uec_trace(scenario, mode):
    path = trace_path(scenario, mode)
    rows = []
    if not os.path.exists(path): return rows
    with open(path, errors="ignore") as fp:
        for line in fp:
            m = TRACE_RE.match(line)
            if m: rows.append(kv_parse(m.group(1)))
    return rows


def read_switch_trace(scenario, mode):
    path = trace_path(scenario, mode)
    rows = []
    if not os.path.exists(path): return rows
    with open(path, errors="ignore") as fp:
        for line in fp:
            m = SW_RE.match(line)
            if m: rows.append(kv_parse(m.group(1)))
    return rows


def read_hpcc_ack(scenario, src_id=0):
    path = trace_path(scenario, "hpcc")
    rows = []
    if not os.path.exists(path): return rows
    with open(path, errors="ignore") as fp:
        for line in fp:
            m = HPCC_RE.match(line)
            if not m: continue
            ackno, t_us, src = int(m.group(1)), float(m.group(2)), int(m.group(3))
            if src == src_id:
                rows.append((t_us, ackno))
    return rows


def ack_events_uec(rows):
    out = []
    for r in rows:
        t = fval(r.get("t_us", "0"))
        nb = fval(r.get("newly_acked_bytes", "0"))
        if t > 0 and nb > 0: out.append((t, nb))
    return out


def ack_events_hpcc(rows):
    rows = sorted(rows)
    out, prev = [], 0
    for t, ack in rows:
        d = ack - prev
        prev = ack
        if d > 0: out.append((t, float(d)))
    return out


def load_events(scenario, mode):
    if mode == "hpcc":
        return ack_events_hpcc(read_hpcc_ack(scenario))
    return ack_events_uec(read_uec_trace(scenario, mode))

# ---------------------------------------------------------------- metrics table ----

CSIG_FLOW_RE = re.compile(
    r"^CSIG_FLOW\s+t_us=([0-9.eE+-]+)\s+flow=(\d+)\s+newly_acked_bytes=(\d+)")


def ack_events_uec_by_flow_csig_flow(scenario, mode):
    """Parse the lightweight `CSIG_FLOW` lines emitted for every
    flow on every ACK. Used for per-flow / Jain-fairness metrics.

    Falls back to the legacy `CSIG_TRACE` parser when no CSIG_FLOW rows are
    found.
    """
    path = trace_path(scenario, mode)
    out = defaultdict(list)
    if not os.path.exists(path):
        return out
    with open(path, errors="ignore") as fp:
        for line in fp:
            m = CSIG_FLOW_RE.match(line)
            if not m:
                continue
            t = float(m.group(1))
            flow = int(m.group(2))
            nb = float(m.group(3))
            if t > 0 and nb > 0:
                out[flow].append((t, nb))
    return out


def ack_events_uec_by_flow(rows):
    """Legacy single-flow parser kept for backward-compat with traces that
    only contain CSIG_TRACE rows (pre-CSIG_FLOW). Returns a dict keyed by
    flow id, but in practice only the debug flow will be present.
    """
    out = defaultdict(list)
    for r in rows:
        t = fval(r.get("t_us", "0"))
        nb = fval(r.get("newly_acked_bytes", "0"))
        flow = int(fval(r.get("flow", "-1")))
        if flow >= 0 and t > 0 and nb > 0:
            out[flow].append((t, nb))
    return out


def ack_events_hpcc_by_flow(scenario):
    """
    Parses HPCC CWND ACKNO lines into per-src ack delta events.

    Returns:
        dict[src_id] -> list[(t_us, newly_acked_bytes)]
    """
    path = trace_path(scenario, "hpcc")
    per_src = defaultdict(list)

    if not os.path.exists(path):
        return per_src

    raw = defaultdict(list)

    with open(path, errors="ignore") as fp:
        for line in fp:
            m = HPCC_RE.match(line)
            if not m:
                continue
            ackno = int(m.group(1))
            t_us = float(m.group(2))
            src = int(m.group(3))
            raw[src].append((t_us, ackno))

    for src, rows in raw.items():
        rows = sorted(rows)
        prev = 0
        for t_us, ackno in rows:
            delta = ackno - prev
            prev = ackno
            if delta > 0:
                per_src[src].append((t_us, float(delta)))

    return per_src


def load_events_by_flow(scenario, mode):
    if mode == "hpcc":
        return ack_events_hpcc_by_flow(scenario)
    # Prefer CSIG_FLOW emission (one row per flow per ACK,
    # 3 fields). Fall back to the verbose CSIG_TRACE rows only if the trace
    # predates the CSIG_FLOW emission, in which case only the debug flow
    # will be visible and `fairness_valid` will end up False as expected.
    by_flow = ack_events_uec_by_flow_csig_flow(scenario, mode)
    if by_flow:
        return by_flow
    return ack_events_uec_by_flow(read_uec_trace(scenario, mode))


def bytes_in_window(events, start_us, end_us):
    return sum(nb for t, nb in events if start_us <= t < end_us)


def gbps_from_bytes(num_bytes, duration_us):
    if duration_us <= 0:
        return 0.0
    return num_bytes * 8.0 / (duration_us * 1e-6) / 1e9


def jain(xs):
    xs = [x for x in xs if x >= 0]
    if not xs:
        return 0.0
    s = sum(xs)
    ss = sum(x * x for x in xs)
    if ss == 0:
        return 0.0
    return (s * s) / (len(xs) * ss)


def stage_windows_mn():
    windows = []
    for i, (m, n, start_us) in enumerate(MN_STAGES):
        end_us = MN_STAGES[i + 1][2] if i + 1 < len(MN_STAGES) else MN_END_US
        windows.append({
            "stage": "%d-%d ms" % (start_us // 1000, end_us // 1000),
            "start_us": start_us,
            "end_us": end_us,
            "M": m,
            "N": n,
            # In the M/N setup, victim competes against max(M+1, N+1) effective contenders.
            # This matches fair_share_line().
            "fair_share_gbps": LINK_GBPS / max(m + 1, n + 1),
            "active_expected": max(m + 1, n + 1),
        })
    return windows


def stage_windows_hc():
    windows = []
    for i, (n, start_us) in enumerate(HC_STAGES):
        end_us = HC_STAGES[i + 1][1] if i + 1 < len(HC_STAGES) else 100000
        windows.append({
            "stage": "%d flows" % n,
            "start_us": start_us,
            "end_us": end_us,
            "M": "",
            "N": n,
            "fair_share_gbps": LINK_GBPS / n,
            "active_expected": n,
        })
    return windows


def summarize_stage_metrics(scenario, modes, windows, tracked_flow_default=0):
    """Per-stage metrics. Presentation-safe.

    If the parser only observed one flow, that single flow is taken as the
    tracked/victim flow (logs only emit `CSIG_TRACE` for the tracked
    source; other sources are deliberately silent). `jain_observed` is
    set to NaN and `fairness_valid=False` unless every expected active
    flow was observed.

    The single-flow throughput is reported as `tracked_flow_gbps`, never
    as "aggregate throughput", because summing over partial flows would
    be misleading.
    """
    rows = []

    for mode in modes:
        per_flow = load_events_by_flow(scenario, mode)

        for w in windows:
            start_us = w["start_us"]
            end_us = w["end_us"]
            duration_us = end_us - start_us

            flow_goodputs = {}
            for flow, events in per_flow.items():
                b = bytes_in_window(events, start_us, end_us)
                g = gbps_from_bytes(b, duration_us)
                if g > 0:
                    flow_goodputs[flow] = g

            active_observed = len(flow_goodputs)
            active_expected = w["active_expected"]
            fair_share = w["fair_share_gbps"]

            # Tracked flow selection:
            #   - default tracked ID if observed, else
            #   - the unique observed flow if there is exactly one, else
            #   - nothing (tracked_flow_gbps = 0).
            if tracked_flow_default in flow_goodputs:
                tracked_flow_id = tracked_flow_default
            elif active_observed == 1:
                tracked_flow_id = next(iter(flow_goodputs))
            else:
                tracked_flow_id = tracked_flow_default

            tracked_gbps = flow_goodputs.get(tracked_flow_id, 0.0)
            tracked_ratio = tracked_gbps / fair_share if fair_share > 0 else 0.0

            aggregate_observed = sum(flow_goodputs.values())

            fairness_valid = (active_observed >= active_expected
                              and active_observed > 1)
            jain_observed = (jain(list(flow_goodputs.values()))
                             if fairness_valid else float("nan"))

            rows.append({
                "scenario": scenario,
                "mode": LABEL.get(mode, mode),
                "stage": w["stage"],
                "M": w["M"],
                "N": w["N"],
                "tracked_flow_id": tracked_flow_id,
                "tracked_flow_gbps": tracked_gbps,
                "fair_share_gbps": fair_share,
                "tracked_over_fair": tracked_ratio,
                "active_observed": active_observed,
                "active_expected": active_expected,
                "aggregate_observed_gbps": aggregate_observed,
                "jain_observed": jain_observed,
                "fairness_valid": fairness_valid,
            })

    return rows


# Schema for both CSV and Markdown outputs. Kept as one source of truth so
# that consumers of metrics_summary.{csv,md} don't diverge.
_METRICS_FIELDS = [
    "scenario",
    "mode",
    "stage",
    "M",
    "N",
    "tracked_flow_id",
    "tracked_flow_gbps",
    "fair_share_gbps",
    "tracked_over_fair",
    "active_observed",
    "active_expected",
    "aggregate_observed_gbps",
    "jain_observed",
    "fairness_valid",
]

_METRICS_FLOAT_FIELDS = {
    "tracked_flow_gbps",
    "fair_share_gbps",
    "tracked_over_fair",
    "aggregate_observed_gbps",
    "jain_observed",
}


def _fmt_metric(field, v):
    if field in _METRICS_FLOAT_FIELDS:
        if isinstance(v, float) and math.isnan(v):
            return "NaN"
        return "%.4f" % v
    if field == "fairness_valid":
        return "True" if v else "False"
    return str(v)


def write_metrics_csv(rows, out_csv):
    import csv

    with open(out_csv, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(_METRICS_FIELDS)
        for r in rows:
            writer.writerow([_fmt_metric(f, r[f]) for f in _METRICS_FIELDS])

    print("# wrote %s" % out_csv)


def write_metrics_markdown(rows, out_md):
    md_fields = [
        "scenario",
        "mode",
        "stage",
        "tracked_flow_id",
        "tracked_flow_gbps",
        "fair_share_gbps",
        "tracked_over_fair",
        "active_observed",
        "active_expected",
        "jain_observed",
        "fairness_valid",
    ]

    with open(out_md, "w") as fp:
        fp.write(
            "> Note: `jain_observed` is only valid when "
            "`fairness_valid = True`. Single-flow traces report "
            "`tracked_flow_gbps` only; they are **not** aggregate "
            "throughput evidence.\n>\n"
            "> `active_expected` = contenders at the victim's bottleneck hop "
            "(`max(M+1, N+1)` for paper14, `N` for paper17). "
            "`active_observed` counts every flow that transmitted ≥1 byte in "
            "the window; for paper14 this legitimately exceeds `active_expected`"
            " because flows from earlier stages remain alive on disjoint hops. "
            "In paper14 `jain_observed` is Jain across **all** live flows and "
            "is expected to be <1 since disjoint-hop flows run at different "
            "single-hop rates. In paper17 (shared bottleneck) `jain_observed` "
            "is the standard fairness index.\n\n")
        fp.write("| " + " | ".join(md_fields) + " |\n")
        fp.write("|" + "|".join(["---"] * len(md_fields)) + "|\n")

        for r in rows:
            vals = [_fmt_metric(f, r[f]) for f in md_fields]
            fp.write("| " + " | ".join(vals) + " |\n")

    print("# wrote %s" % out_md)


def metrics_tables():
    """
    Produces:
      figs/metrics_summary.csv
      figs/metrics_summary.md
    """
    all_rows = []

    # Tracked/victim flow is `flow=1` because `htsim_uec` is invoked with
    # `-debug_flowid 1`, and `CSIG_FLOW flow=<flow_id>` uses the same
    # `_flow.flow_id()` the simulator assigns 1 to the first (victim) flow.
    TRACKED = 1

    # M/N multihop: same modes as main plot.
    all_rows.extend(
        summarize_stage_metrics(
            scenario="paper14_multihop_mn",
            modes=MAIN_MODES,
            windows=stage_windows_mn(),
            tracked_flow_default=TRACKED,
        )
    )

    # High concurrency.
    all_rows.extend(
        summarize_stage_metrics(
            scenario="paper17_high_concurrency",
            modes=MAIN_MODES,
            windows=stage_windows_hc(),
            tracked_flow_default=TRACKED,
        )
    )

    write_metrics_csv(all_rows, os.path.join(FIGS_DIR, "metrics_summary.csv"))
    write_metrics_markdown(all_rows, os.path.join(FIGS_DIR, "metrics_summary.md"))


def auto_end_us(events_per_mode, fallback):
    last = 0.0
    for ev in events_per_mode.values():
        if ev: last = max(last, ev[-1][0])
    return last if last > 0 else float(fallback)


def throughput_bins(events, end_us, bin_us):
    n = max(1, int(math.ceil(end_us / bin_us)))
    bytes_b = np.zeros(n)
    for t, nb in events:
        i = int(t / bin_us)
        if 0 <= i < n: bytes_b[i] += nb
    gbps = bytes_b * 8.0 / (bin_us * 1e-6) / 1e9
    centers_ms = (np.arange(n) + 0.5) * bin_us / 1000.0
    return centers_ms, gbps


def smooth(y, w=3):
    if len(y) < w: return y
    return np.convolve(y, np.ones(w) / w, mode="same")


def downsample(xs, ys, max_pts=4000):
    n = len(xs)
    if n <= max_pts or n == 0: return xs, ys
    s = max(1, n // max_pts)
    return xs[::s], ys[::s]


def interp_series(rows, field):
    xs, ys = [], []
    for r in rows:
        t = fval(r.get("t_us", "0")) / 1000.0
        v = fval(r.get(field, "0"))
        if t >= 0:
            xs.append(t); ys.append(v)
    return np.array(xs), smooth(np.array(ys), 5) if ys else np.array([])


def switch_delay_by_class(rows, which):
    pts = defaultdict(float)
    for r in rows:
        st = int(fval(r.get("switch_type", "0")))
        d  = int(fval(r.get("direction", "0")))
        if which == "src" and not (st == 1 and d == 1): continue
        if which == "dst" and not (st == 2 and d == 2): continue
        t = round(fval(r.get("t_us", "0")) / 1000.0, 4)
        v = fval(r.get("local_delay_ns", "0")) / 1000.0
        pts[t] = max(pts[t], v)
    xs = sorted(pts); ys = [pts[t] for t in xs]
    return np.array(xs), smooth(np.array(ys), 7) if ys else np.array([])


def add_mn_top_axis(ax):
    ticks, labels = [], []
    for i, (m, n, start) in enumerate(MN_STAGES):
        end = MN_STAGES[i + 1][2] if i + 1 < len(MN_STAGES) else MN_END_US
        ticks.append((start + end) / 2.0 / 1000.0)
        labels.append("%d\n%d" % (m, n))
    top = ax.secondary_xaxis("top")
    top.set_xticks(ticks); top.set_xticklabels(labels)
    ax.text(-0.085, 1.16, "M\nN", transform=ax.transAxes,
            ha="right", va="center", fontsize=9)


def fair_share_line():
    xs, ys = [], []
    for i, (m, n, start) in enumerate(MN_STAGES):
        end = MN_STAGES[i + 1][2] if i + 1 < len(MN_STAGES) else MN_END_US
        fair = LINK_GBPS / max(m + 1, n + 1)
        xs += [start / 1000.0, end / 1000.0]; ys += [fair, fair]
    return xs, ys


def hc_fair_share_line():
    xs, ys = [], []
    for i, (n, start) in enumerate(HC_STAGES):
        end = HC_STAGES[i + 1][1] if i + 1 < len(HC_STAGES) else 100000
        fair = LINK_GBPS / n
        xs += [start / 1000.0, end / 1000.0]; ys += [fair, fair]
    return xs, ys


def add_hc_top_axis(ax):
    ticks, labels = [], []
    for i, (n, start) in enumerate(HC_STAGES):
        end = HC_STAGES[i + 1][1] if i + 1 < len(HC_STAGES) else 100000
        ticks.append((start + end) / 2.0 / 1000.0)
        labels.append(str(n))
    top = ax.secondary_xaxis("top")
    top.set_xticks(ticks); top.set_xticklabels(labels)
    top.set_xlabel("Concurrent flows")


def add_stage_dividers(ax, stages, idx_start, end_ms):
    for stage in stages[1:]:
        s = stage[idx_start]
        if s / 1000.0 <= end_ms:
            ax.axvline(s / 1000.0, color="0.78", linestyle="-", linewidth=0.6)


def save(fig, name):
    png = os.path.join(FIGS_DIR, name + ".png")
    pdf = os.path.join(FIGS_DIR, name + ".pdf")
    fig.savefig(png); fig.savefig(pdf); plt.close(fig)
    print("# wrote %s" % png)


# ---------------------------------------------------------------- figures ----

def fig14_multihop():
    """Multi-hop M/N congestion: (a) victim throughput, (b) victim delay
    signal each controller consumed, (c) target and per-hop delays."""
    sc = "paper14_multihop_mn"
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 3.6))

    # (a) Victim throughput — all four modes including HPCC.
    events = {m: load_events(sc, m) for m in MAIN_MODES}
    end_us = auto_end_us(events, 500000)
    for m in MAIN_MODES:
        x, y = throughput_bins(events[m], end_us, 1000.0)
        axes[0].plot(x, smooth(y, 3), color=COLOR[m], linewidth=1.4,
                     linestyle=LINESTYLE[m], label=LABEL[m])
    fx, fy = fair_share_line()
    axes[0].plot(fx, fy, color="0.5", linestyle=":", linewidth=1.2, label="Fair share")
    axes[0].set_xlim(0, end_us / 1000.0); axes[0].set_ylim(bottom=0)
    axes[0].set_xlabel("Time (ms)"); axes[0].set_ylabel("Victim throughput (Gbps)")
    axes[0].set_title("(a) Victim throughput")
    add_mn_top_axis(axes[0])
    add_stage_dividers(axes[0], MN_STAGES, 2, end_us / 1000.0)
    axes[0].legend(loc="upper right", ncol=1)

    # (b) Victim delay signal: NSCC RTT path-delay vs CSIG max-hop delay.
    base = read_uec_trace(sc, "baseline_rtt")
    bx, by = interp_series(base, "rtt_delay_us_counterfactual")
    bx, by = downsample(bx, by)
    axes[1].plot(bx, by, color=COLOR["baseline_rtt"], linewidth=1.3,
                 label="RTT path delay (NSCC)")
    rows = read_uec_trace(sc, "csig_poseidon_rate")
    cx, cy = interp_series(rows, "csig_delay_us")
    cx, cy = downsample(cx, cy)
    axes[1].plot(cx, cy, color=COLOR["csig_poseidon_rate"], linewidth=1.2,
                 label="CSIG max-hop delay")
    axes[1].set_xlim(0, end_us / 1000.0)
    axes[1].set_xlabel("Time (ms)"); axes[1].set_ylabel("Delay signal (μs)")
    axes[1].set_title("(b) Victim delay signal")
    add_mn_top_axis(axes[1])
    add_stage_dividers(axes[1], MN_STAGES, 2, end_us / 1000.0)
    axes[1].legend(loc="upper right")

    # (c) Per-hop local delays + victim target (csig_poseidon_rate).
    sw = read_switch_trace(sc, "csig_poseidon_rate")
    sx, sy = switch_delay_by_class(sw, "src"); sx, sy = downsample(sx, sy)
    dx, dy = switch_delay_by_class(sw, "dst"); dx, dy = downsample(dx, dy)
    rows = read_uec_trace(sc, "csig_poseidon_rate")
    tx, ty = interp_series(rows, "effective_target_us")
    tx, ty = downsample(tx, ty)
    axes[2].plot(dx, dy, color="#0072B2", linewidth=1.3, label="Dst-side hop delay")
    axes[2].plot(sx, sy, color="#009E73", linewidth=1.3, label="Src-side hop delay")
    axes[2].plot(tx, ty, color="#D55E00", linewidth=1.4, label="Victim target")
    axes[2].set_xlim(0, end_us / 1000.0)
    axes[2].set_xlabel("Time (ms)"); axes[2].set_ylabel("Delay / target (μs)")
    axes[2].set_title("(c) Target and per-hop delays")
    add_mn_top_axis(axes[2])
    add_stage_dividers(axes[2], MN_STAGES, 2, end_us / 1000.0)
    axes[2].legend(loc="upper right")

    fig.tight_layout(w_pad=2.0)
    save(fig, "fig14_multihop")

    caption = {
    "scenario": sc,
    "stages": [{"M": m, "N": n, "start_ms": s/1000, "fair_gbps": LINK_GBPS/max(m+1,n+1)} 
               for m,n,s in MN_STAGES],
    "modes_shown": [LABEL[m] for m in MAIN_MODES],
    "end_ms": end_us / 1000,
    }
    with open(os.path.join(FIGS_DIR, "fig14_caption.json"), "w") as fp:
        json.dump(caption, fp, indent=2)


def fig21a_ablation():
    """Signal vs controller ablation: (a) throughput, (b) delay signal
    consumed. Holding the signal fixed across CSIG-* modes isolates the
    contribution of the target/cwnd controller."""
    sc = "paper14_multihop_mn"
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 3.7))

    events = {m: load_events(sc, m) for m in ABLATION_MODES}
    end_us = auto_end_us(events, 500000)
    for m in ABLATION_MODES:
        x, y = throughput_bins(events[m], end_us, 1000.0)
        axes[0].plot(x, smooth(y, 3), color=COLOR[m], linewidth=1.4,
                     linestyle=LINESTYLE[m], label=LABEL[m])
    fx, fy = fair_share_line()
    axes[0].plot(fx, fy, color="0.5", linestyle=":", linewidth=1.2, label="Fair share")
    axes[0].set_xlim(0, end_us / 1000.0); axes[0].set_ylim(bottom=0)
    axes[0].set_xlabel("Time (ms)"); axes[0].set_ylabel("Victim throughput (Gbps)")
    axes[0].set_title("(a) Throughput")
    add_mn_top_axis(axes[0])
    add_stage_dividers(axes[0], MN_STAGES, 2, end_us / 1000.0)
    axes[0].legend(loc="upper right")

    for m in ABLATION_MODES:
        rows = read_uec_trace(sc, m)
        field = "rtt_delay_us_counterfactual" if m == "baseline_rtt" else "csig_delay_us"
        x, y = interp_series(rows, field)
        x, y = downsample(x, y)
        axes[1].plot(x, y, color=COLOR[m], linewidth=1.2,
                     linestyle=LINESTYLE[m], label=LABEL[m])
    axes[1].set_xlim(0, end_us / 1000.0)
    axes[1].set_xlabel("Time (ms)")
    axes[1].set_ylabel("Delay consumed by controller (μs)")
    axes[1].set_title("(b) Delay signal consumed")
    add_mn_top_axis(axes[1])
    add_stage_dividers(axes[1], MN_STAGES, 2, end_us / 1000.0)
    axes[1].legend(loc="upper right")

    fig.tight_layout(w_pad=2.0)
    save(fig, "fig21a_ablation")


def fig17_concurrency():
    """Stability under high concurrency: tracked-flow throughput as the
    number of concurrent flows increases from 50 to 200 in 25 ms steps.
    UEC modes only; HPCC is excluded because (a) the tracked HPCC source
    completes its 60 MB flow at ~39 ms (ACKNO reaches flow size), so
    plotting its line beyond that point would represent a finished flow,
    not throughput, and (b) the lossless queue still overflows ~241k
    times under this incast even with -q 36, so HPCC is not in a regime
    where fairness comparison is meaningful."""
    sc = "paper17_high_concurrency"
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    events = {m: load_events(sc, m) for m in MAIN_MODES}
    end_us = auto_end_us(events, 100000)
    for m in MAIN_MODES:
        x, y = throughput_bins(events[m], end_us, 1000.0)
        ax.plot(x, smooth(y, 3), color=COLOR[m], linewidth=1.4,
                linestyle=LINESTYLE[m], label=LABEL[m])
    hx, hy = hc_fair_share_line()
    ax.plot(hx, hy, color="0.5", linestyle=":", linewidth=1.2, label="Fair share")
    add_stage_dividers(ax, [(s, t) for s, t in HC_STAGES], 1, end_us / 1000.0)
    ax.set_xlim(0, end_us / 1000.0); ax.set_ylim(bottom=0)
    ax.set_xlabel("Time (ms)"); ax.set_ylabel("Tracked-flow throughput (Gbps)")
    ax.set_title("Stability under high concurrency")
    add_hc_top_axis(ax)
    ax.legend(loc="upper right", ncol=2)
    fig.tight_layout()
    save(fig, "fig17_concurrency")


def main():
    print("# RAW_DIR = %s" % RAW_DIR)
    if not os.path.isdir(RAW_DIR):
        raise SystemExit("FATAL: raw dir not found: %s" % RAW_DIR)

    fig14_multihop()
    fig21a_ablation()
    fig17_concurrency()

    metrics_tables()

    print("# done. figs and metrics in %s" % FIGS_DIR)


if __name__ == "__main__":
    main()
