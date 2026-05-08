#!/usr/bin/env python3
"""Parse all raw outputs in results/raw into CSVs and a terse verdict."""

import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_DIR = os.path.dirname(HERE)
RAW_DIR = os.path.join(HARNESS_DIR, "results", "raw")
RESULTS_DIR = os.path.join(HARNESS_DIR, "results")
TRACES_DIR = os.path.join(RESULTS_DIR, "traces")
CM_DIR = os.path.join(HARNESS_DIR, "cm")

sys.path.insert(0, HERE)
from parse_run import aggregate, parse  # noqa: E402
from parse_trace import parse_one as parse_trace_one, write_csv as write_trace_csv  # noqa: E402
import derive_metrics  # noqa: E402

MODES = (
    "baseline_rtt",
    "hpcc",
    "csig_poseidon_rate",
    "csig_delay_abw",
)
MODE_RE = "|".join(MODES)
RAW_RE = re.compile(r"^(.+)__(%s)\.out$" % MODE_RE)
TRACE_RE = re.compile(r"^(.+)__(%s)\.trace\.out$" % MODE_RE)

RUN_FIELDS = [
    "scenario", "mode", "family", "fanin", "msg_bytes",
    "n_flows", "linkspeed_gbps",
    "fct_us_max", "fct_us_p99", "fct_us_min", "fct_us_mean",
    "goodput_gbps_max", "goodput_gbps_min", "goodput_gbps_mean", "jfi_goodput",
    "pkts_new", "pkts_rtx", "pkts_nacks", "delivered_mb", "rtx_per_mb",
    "wallclock_s", "multi_dec_total", "fair_inc_total", "prop_inc_total",
    "fast_inc_total", "eta_inc_total",
]
FLOW_FIELDS = [
    "scenario", "mode", "family", "flow_id", "name", "src", "dst",
    "start_us", "declared_size_bytes", "fct_us", "total_pkts", "total_bytes",
    "goodput_gbps", "fair_inc", "prop_inc", "fast_inc", "eta_inc",
    "multi_dec", "quick_dec", "nack_dec",
]


def scenario_meta(scenario):
    family = scenario.split("_", 1)[0]
    fanin = ""
    msg_bytes = ""
    m = re.search(r"incast_(\d+)_([0-9]+)(K|MB)", scenario)
    if m:
        fanin = int(m.group(1))
        val = int(m.group(2))
        msg_bytes = val * (1000 if m.group(3) == "K" else 1_000_000)
    elif scenario.startswith("C_queue_pressure_32"):
        family, fanin, msg_bytes = "C", 32, 1_000_000
    return {"family": family, "fanin": fanin, "msg_bytes": msg_bytes}


def cm_for_scenario(scenario):
    mapping = {
        "A1_lowload_1f": "A1_lowload_1f.cm",
        "A2_lowload_4f": "A2_lowload_4f.cm",
        "B_incast_4_256K": "B_incast_4_256K.cm",
        "B_incast_8_256K": "B_incast_8.cm",
        "B_incast_16_256K": "B_incast_16.cm",
        "B_incast_32_256K": "B_incast_32.cm",
        "B_incast_64_256K": "B_incast_64_256K.cm",
        "B_incast_4_1MB": "B_incast_4_1MB.cm",
        "B_incast_8_1MB": "B_incast_8_1MB.cm",
        "B_incast_16_1MB": "B_incast_16_1MB.cm",
        "B_incast_32_1MB": "B_incast_32_1MB.cm",
        "B_incast_64_1MB": "B_incast_64_1MB.cm",
        "C_queue_pressure_32": "C_queue_pressure_32_1MB.cm",
        "D_mixed_recovery": "D_mixed_recovery.cm",
        "E_multihop_fairness": "E_multihop_fairness.cm",
        "F_reverse_path": "F_reverse_path.cm",
    }
    name = mapping.get(scenario)
    return os.path.join(CM_DIR, name) if name else None


def write_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def verdict(rows):
    by = {(r["scenario"], r["mode"]): r for r in rows}
    derived = {}
    derived_path = os.path.join(RESULTS_DIR, "derived_metrics.csv")
    if os.path.exists(derived_path):
        with open(derived_path, newline="") as fp:
            for r in csv.DictReader(fp):
                derived[(r["scenario"], r["mode"])] = r
    lines = [
        "# CSIG delay+ABW Verdict",
        "",
        "Mode set: `baseline_rtt`, `hpcc`, `csig_poseidon_rate`, "
        "`csig_delay_abw`.",
        "",
        "Harness-selected `csig_delay_abw` defaults: `target_divisor=2.0`, "
        "`abw_gain=0.125`, `delay_low_frac=0.75`. These are sweep-selected "
        "balanced values from `results/delay_abw_sweep.csv`, not simulator-wide "
        "defaults.",
        "",
        "HPCC is included for FCT/fairness context. Its retransmit/NACK fields "
        "are not directly comparable to UEC/NSCC counters in this parser, so "
        "loss-pressure claims should use the UEC-derived modes only.",
        "",
        "## Headline Table",
        "",
        "| scenario | mode | flows | max FCT us | p99 FCT us | JFI | rtx | NACKs | rtx/MB |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append("| {scenario} | {mode} | {n_flows} | {fct_us_max:.1f} | {fct_us_p99:.1f} | {jfi_goodput:.4f} | {pkts_rtx} | {pkts_nacks} | {rtx_per_mb:.2f} |".format(
            scenario=r["scenario"], mode=r["mode"],
            n_flows=int(r["n_flows"]),
            fct_us_max=float(r["fct_us_max"]),
            fct_us_p99=float(r["fct_us_p99"]),
            jfi_goodput=float(r["jfi_goodput"]),
            pkts_rtx=int(r["pkts_rtx"]),
            pkts_nacks=int(r["pkts_nacks"]),
            rtx_per_mb=float(r["rtx_per_mb"]),
        ))

    lines += ["", "## Automatic Reading", ""]
    interesting = [
        "B_incast_32_1MB",
        "C_queue_pressure_32",
        "D_mixed_recovery",
        "E_multihop_fairness",
        "F_reverse_path",
    ]
    for sc in interesting:
        base = by.get((sc, "baseline_rtt"))
        dual = by.get((sc, "csig_delay_abw"))
        pose = by.get((sc, "csig_poseidon_rate"))
        if not (base and dual):
            continue
        def pct(a, b):
            return 100.0 * (float(a) - float(b)) / float(b) if float(b) else 0.0
        msg = "- `%s`: csig_delay_abw vs baseline maxFCT %+0.1f%%, rtx %+d" % (
            sc,
            pct(dual["fct_us_max"], base["fct_us_max"]),
            int(dual["pkts_rtx"]) - int(base["pkts_rtx"]),
        )
        if pose:
            msg += "; vs Poseidon-rate maxFCT %+0.1f%%, rtx %+d" % (
                pct(dual["fct_us_max"], pose["fct_us_max"]),
                int(dual["pkts_rtx"]) - int(pose["pkts_rtx"]),
            )
        lines.append(msg + ".")

    lines += ["", "## Derived Trace Scalars", ""]
    for sc in ("C_queue_pressure_32", "D_mixed_recovery", "E_multihop_fairness"):
        lines.append("### `%s`" % sc)
        lines.append("")
        lines.append("| mode | CSIG overshoot us^2 | recovery us | peak CSIG us | time to 90% fair us |")
        lines.append("|---|---:|---:|---:|---:|")
        for mode in ("csig_poseidon_rate", "csig_delay_abw"):
            r = derived.get((sc, mode), {})
            def gv(k):
                try:
                    return float(r.get(k, ""))
                except ValueError:
                    return -1.0
            lines.append("| `%s` | %.1f | %.1f | %.2f | %.1f |" % (
                mode,
                gv("overshoot_area_us2"),
                gv("recovery_time_us"),
                gv("peak_csig_delay_us"),
                gv("time_to_90pct_fair_us"),
            ))
        lines.append("")

    lines += [
        "",
        "## Reading Notes",
        "",
        "- The headline table, automatic deltas, and derived trace scalar table "
        "above are generated from the current CSV inputs. Rerun this parser "
        "after every new sweep; do not carry this Markdown verdict forward as "
        "a static claim.",
        "- Treat HPCC as external context for FCT and fairness only. Its counters "
        "are parsed from a different controller path and should not be compared "
        "directly against UEC/NSCC retransmit or NACK counters.",
        "- For paper claims, use the generated deltas plus the trace figures. "
        "Do not infer controller correctness from max FCT alone.",
        "",
    ]
    return "\n".join(lines)


def main():
    run_rows = []
    flow_rows = []
    if not os.path.isdir(RAW_DIR):
        sys.exit("missing raw dir: %s" % RAW_DIR)

    for name in sorted(os.listdir(RAW_DIR)):
        if name.startswith("SMOKE__"):
            continue
        t = TRACE_RE.match(name)
        if t:
            scenario, mode = t.groups()
            rows = parse_trace_one(os.path.join(RAW_DIR, name))
            dst = os.path.join(TRACES_DIR, "%s__%s.trace.csv" % (scenario, mode))
            write_trace_csv(rows, dst)
            continue
        m = RAW_RE.match(name)
        if not m:
            continue
        scenario, mode = m.groups()
        path = os.path.join(RAW_DIR, name)
        flows, summary, linkspeed, wallclock = parse(path, cm_for_scenario(scenario))
        agg = aggregate(flows, summary, linkspeed, wallclock)
        if not agg:
            continue
        meta = scenario_meta(scenario)
        row = {"scenario": scenario, "mode": mode, **meta, **agg}
        run_rows.append(row)
        for flow in flows:
            flow_rows.append({"scenario": scenario, "mode": mode, **meta, **flow})

    mode_index = {m: i for i, m in enumerate(MODES)}
    run_rows.sort(key=lambda r: (r["scenario"], mode_index.get(r["mode"], 99)))
    flow_rows.sort(key=lambda r: (r["scenario"], mode_index.get(r["mode"], 99), int(r["flow_id"])))

    write_csv(os.path.join(RESULTS_DIR, "runs.csv"), RUN_FIELDS, run_rows)
    write_csv(os.path.join(RESULTS_DIR, "per_flow.csv"), FLOW_FIELDS, flow_rows)
    derive_metrics.main()
    with open(os.path.join(RESULTS_DIR, "verdict.md"), "w") as fp:
        fp.write(verdict(run_rows))
    print("# wrote %d run rows, %d flow rows" % (len(run_rows), len(flow_rows)))


if __name__ == "__main__":
    main()
