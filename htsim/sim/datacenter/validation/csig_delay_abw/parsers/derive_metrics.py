#!/usr/bin/env python3
"""
Derive scalar control-law metrics from CSIG_TRACE CSVs.

Output: results/derived_metrics.csv with columns
    scenario, mode, flow_id,
    overshoot_area_us2,         # ∫ max(0, csig_delay - T_hop) dt
    recovery_time_us,           # first t after peak where csig_delay <= T_hop
    peak_csig_delay_us,
    rtt_overshoot_area_us2,     # baseline-equivalent: ∫ max(0, rtt_delay - T_path) dt
    rtt_recovery_time_us,
    peak_rtt_delay_us,
    time_to_90pct_fair_us,      # first t where cwnd_after >= 0.9 * fair_share_cwnd
    fair_share_cwnd_bytes,      # estimated as maxwnd_seen / N_concurrent (passed in)
    delivered_bytes,            # last cumulative ACK or sum of newly_acked
    n_acks,
    csig_delay_p50_us, csig_delay_p99_us,
    rtt_delay_p50_us, rtt_delay_p99_us

Heuristic for `fair_share_cwnd_bytes`: if scenario id matches a known incast
fan-in pattern (B_incast_<N>_..., C_queue_pressure_<N>_...), use cwnd_max / N
where cwnd_max is the largest `cwnd_after_bytes` observed across all modes
for that scenario+flow. Otherwise mark as missing (-1).

Stdlib only.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_DIR = os.path.dirname(HERE)
TRACES_DIR = os.path.join(HARNESS_DIR, "results", "traces")
OUT_CSV = os.path.join(HARNESS_DIR, "results", "derived_metrics.csv")

FANIN_RE = re.compile(r"^(?:B_incast|C_queue_pressure)_(\d+)(?:[_.]|$)")
ALLOWED_MODES = {
    "baseline_rtt",
    "csig_poseidon_rate",
    "csig_delay_abw",
}

# T_path comes from htsim_uec default _target_Qdelay = 6 µs (printed at startup
# but not always parseable from the .trace.out without grepping; hard-code the
# default here and let scenarios override via env if needed).
DEFAULT_T_PATH_US = 6.0
DEFAULT_T_HOP_DIVISOR = 3.0


def _f(d, k, default=0.0):
    v = d.get(k, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def fan_in_for_scenario(sid):
    m = FANIN_RE.match(sid)
    return int(m.group(1)) if m else 0


def percentile(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def derive(rows, t_hop_us, t_path_us):
    if not rows:
        return None
    rows = [r for r in rows if _f(r, "t_us") > 0]
    if not rows:
        return None

    csig_d   = [(_f(r, "t_us"), _f(r, "csig_delay_us")) for r in rows]
    rtt_d    = [(_f(r, "t_us"), _f(r, "rtt_delay_us_counterfactual")) for r in rows]
    cwnd     = [(_f(r, "t_us"), _f(r, "cwnd_after_bytes")) for r in rows]

    # Trapezoidal integral of max(0, signal - target) dt.  Units: us^2.
    def overshoot_area(series, thresh):
        if len(series) < 2:
            return 0.0
        total = 0.0
        for (t0, v0), (t1, v1) in zip(series, series[1:]):
            o0 = max(0.0, v0 - thresh)
            o1 = max(0.0, v1 - thresh)
            total += 0.5 * (o0 + o1) * (t1 - t0)
        return total

    # First time AFTER the peak where signal returns at or below threshold.
    def recovery_time(series, thresh):
        if not series:
            return -1.0
        peak_idx = max(range(len(series)), key=lambda i: series[i][1])
        t_peak = series[peak_idx][0]
        for (t, v) in series[peak_idx:]:
            if v <= thresh:
                return t - t_peak
        return -1.0

    csig_overshoot = overshoot_area(csig_d, t_hop_us)
    rtt_overshoot  = overshoot_area(rtt_d, t_path_us)
    csig_rec       = recovery_time(csig_d, t_hop_us)
    rtt_rec        = recovery_time(rtt_d, t_path_us)
    csig_peak      = max((v for _, v in csig_d), default=0.0)
    rtt_peak       = max((v for _, v in rtt_d),  default=0.0)

    csig_vals = [v for _, v in csig_d]
    rtt_vals  = [v for _, v in rtt_d]

    delivered = sum(_f(r, "newly_acked_bytes") for r in rows)
    return {
        "overshoot_area_us2":     csig_overshoot,
        "recovery_time_us":       csig_rec,
        "peak_csig_delay_us":     csig_peak,
        "rtt_overshoot_area_us2": rtt_overshoot,
        "rtt_recovery_time_us":   rtt_rec,
        "peak_rtt_delay_us":      rtt_peak,
        "delivered_bytes":        delivered,
        "n_acks":                 len(rows),
        "csig_delay_p50_us":      percentile(csig_vals, 50),
        "csig_delay_p99_us":      percentile(csig_vals, 99),
        "rtt_delay_p50_us":       percentile(rtt_vals, 50),
        "rtt_delay_p99_us":       percentile(rtt_vals, 99),
    }


def time_to_fair_share(rows, fair_share_bytes, frac=0.9):
    if fair_share_bytes <= 0:
        return -1.0
    target = frac * fair_share_bytes
    for r in rows:
        if _f(r, "cwnd_after_bytes") >= target:
            t = _f(r, "t_us")
            if t > 0:
                return t
    return -1.0


def main():
    if not os.path.isdir(TRACES_DIR):
        sys.exit("FATAL: traces dir not found: %s" % TRACES_DIR)
    fname_re = re.compile(r"^(.+?)__(.+?)\.trace\.csv$")

    # Pass 1: gather peak cwnd per (scenario, flow) across modes for the
    # fair-share heuristic.
    peak_cwnd = {}
    for fn in sorted(os.listdir(TRACES_DIR)):
        m = fname_re.match(fn)
        if not m:
            continue
        sc, mode = m.group(1), m.group(2)
        if mode not in ALLOWED_MODES:
            continue
        rows = list(csv.DictReader(open(os.path.join(TRACES_DIR, fn))))
        if not rows:
            continue
        flow = rows[0].get("flow", "1")
        cw = max((_f(r, "cwnd_after_bytes") for r in rows), default=0)
        key = (sc, flow)
        peak_cwnd[key] = max(peak_cwnd.get(key, 0), cw)

    # Pass 2: compute derived metrics per (scenario, mode).
    out_rows = []
    for fn in sorted(os.listdir(TRACES_DIR)):
        m = fname_re.match(fn)
        if not m:
            continue
        sc, mode = m.group(1), m.group(2)
        if mode not in ALLOWED_MODES:
            continue
        rows = list(csv.DictReader(open(os.path.join(TRACES_DIR, fn))))
        if not rows:
            continue
        flow = rows[0].get("flow", "1")

        # T_hop comes from the trace itself if present (csig_delay_abw sets it);
        # otherwise default.
        t_hop_from_trace = max(
            (_f(r, "target_hop_delay_us") for r in rows), default=0.0)
        t_hop = t_hop_from_trace or (DEFAULT_T_PATH_US / DEFAULT_T_HOP_DIVISOR)
        t_path = DEFAULT_T_PATH_US

        m_data = derive(rows, t_hop, t_path)
        if not m_data:
            continue

        n_concurrent = max(fan_in_for_scenario(sc), 1)
        fair_share = peak_cwnd.get((sc, flow), 0) / n_concurrent if n_concurrent else 0
        ttfs = time_to_fair_share(rows, fair_share, frac=0.9)

        out_rows.append({
            "scenario":              sc,
            "mode":                  mode,
            "flow_id":               flow,
            "t_hop_us":              t_hop,
            "t_path_us":             t_path,
            "fair_share_cwnd_bytes": int(fair_share),
            "time_to_90pct_fair_us": ttfs,
            **m_data,
        })

    if not out_rows:
        print("# no trace CSVs to process")
        return

    keys = list(out_rows[0].keys())
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=keys)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print("# wrote %s (%d rows)" % (OUT_CSV, len(out_rows)))


if __name__ == "__main__":
    main()
