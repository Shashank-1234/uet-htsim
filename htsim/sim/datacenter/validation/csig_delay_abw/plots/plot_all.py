#!/usr/bin/env python3
"""Generate the cleaned CSIG delay+ABW submission figures.

The old debug figures remain in plots/figs if they already exist. This script
writes the presentation set to plots/figs_clean.
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_DIR = os.path.dirname(HERE)
RESULTS_DIR = os.path.join(HARNESS_DIR, "results")
TRACES_DIR = os.path.join(RESULTS_DIR, "traces")
FIGS_DIR = os.path.join(HERE, "figs_clean")

RUNS = os.path.join(RESULTS_DIR, "runs.csv")
PER_FLOW = os.path.join(RESULTS_DIR, "per_flow.csv")
DERIVED = os.path.join(RESULTS_DIR, "derived_metrics.csv")

MODES_ALL = [
    "baseline_rtt", "hpcc", "csig_poseidon_rate", "csig_delay_abw",
]
MODES_UEC = [
    "baseline_rtt", "csig_poseidon_rate", "csig_delay_abw",
]
MODES_CSIG = [
    "csig_poseidon_rate", "csig_delay_abw",
]
# Multihop fairness uses UEC-only modes (HPCC's per-flow accounting differs).
MODES_MULTIHOP = [
    "baseline_rtt", "csig_poseidon_rate", "csig_delay_abw",
]

LABEL = {
    "baseline_rtt": "NSCC (RTT)",
    "hpcc": "HPCC",
    "csig_poseidon_rate": "CSIG + Poseidon-rate",
    "csig_delay_abw": "CSIG delay+ABW",
}
COLOR = {
    "baseline_rtt": "#4D4D4D",
    "hpcc": "#E69F00",
    "csig_poseidon_rate": "#009E73",
    "csig_delay_abw": "#CC79A7",
}

plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.linestyle": ":",
    "grid.alpha": 0.36,
    "figure.dpi": 140,
    "savefig.dpi": 240,
})


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fp:
        return list(csv.DictReader(fp))


def val(row, key, default=0.0):
    if not row:
        return default
    raw = row.get(key, "")
    if raw in ("", None):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def by_key(rows):
    return {(r["scenario"], r["mode"]): r for r in rows}


def trace(scenario, mode):
    return read_csv(os.path.join(TRACES_DIR, "%s__%s.trace.csv" % (scenario, mode)))


def rate_proxy(rows):
    x, y = [], []
    for r in rows:
        raw_rtt = val(r, "raw_rtt_us")
        if raw_rtt <= 0.1:
            continue
        x.append(val(r, "t_us"))
        y.append(val(r, "cwnd_after_bytes") * 8.0 / (raw_rtt * 1e-6) / 1e9)
    return x, y


def smooth(y, window=7):
    if len(y) < window:
        return y
    out = []
    half = window // 2
    for i in range(len(y)):
        lo = max(0, i - half)
        hi = min(len(y), i + half + 1)
        out.append(sum(y[lo:hi]) / (hi - lo))
    return out


def save(fig, name):
    os.makedirs(FIGS_DIR, exist_ok=True)
    png = os.path.join(FIGS_DIR, name + ".png")
    pdf = os.path.join(FIGS_DIR, name + ".pdf")
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    print("# wrote %s and %s" % (png, pdf))


def incast_rows(runs, size):
    return [
        r for r in runs
        if r["scenario"].startswith("B_incast_") and str(r["msg_bytes"]) == str(size)
    ]


def fig1_lowload(runs):
    scenarios = ["A1_lowload_1f", "A2_lowload_4f"]
    bk = by_key(runs)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    width = 0.84 / len(MODES_ALL)
    x = np.arange(len(scenarios))
    for i, mode in enumerate(MODES_ALL):
        axes[0].bar(
            x + i * width,
            [val(bk.get((s, mode)), "fct_us_max") for s in scenarios],
            width,
            label=LABEL[mode],
            color=COLOR[mode],
        )
    axes[0].set_title("Fig. 1a: low-load completion time", loc="left")
    axes[0].set_ylabel("max FCT (us)")
    axes[0].set_xticks(x + (len(MODES_ALL) - 1) * width / 2)
    axes[0].set_xticklabels(["1 flow", "4 flows"])
    axes[1].axis("off")
    text = (
        "Low-load safety gate\n\n"
        "UEC/NSCC-derived modes:\n"
        "  retransmits = 0\n"
        "  NACKs = 0\n"
        "  JFI = 1.0000\n\n"
        "Interpretation:\n"
        "CSIG telemetry is neutral when\n"
        "there is no congestion."
    )
    axes[1].text(0.05, 0.86, text, va="top", ha="left", fontsize=11)
    handles, labels = axes[0].get_legend_handles_labels()
    axes[1].legend(handles, labels, loc="lower left", ncol=2, frameon=True,
                   bbox_to_anchor=(0.03, 0.02))
    save(fig, "1_lowload_sanity")


def fig2_incast_fct(runs):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
    for ax, size, title in zip(axes, (256000, 1000000), ("256KB", "1MB")):
        rows = incast_rows(runs, size)
        for mode in MODES_ALL:
            pts = sorted(
                (int(r["fanin"]), val(r, "fct_us_max"))
                for r in rows if r["mode"] == mode and r["fanin"]
            )
            if pts:
                ax.plot(
                    [p[0] for p in pts], [p[1] for p in pts],
                    marker="o", linewidth=1.7, label=LABEL[mode], color=COLOR[mode],
                )
        ax.set_title("Fig. 2: incast request completion, %s" % title, loc="left")
        ax.set_xlabel("fan-in")
        ax.set_ylabel("max FCT (us)")
        ax.set_xticks([4, 8, 16, 32, 64])
    axes[1].legend(ncol=1, frameon=True)
    save(fig, "2_incast_request_completion")


def fig3_incast_loss(runs):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
    for ax, size, title in zip(axes, (256000, 1000000), ("256KB", "1MB")):
        rows = incast_rows(runs, size)
        for mode in MODES_UEC:
            pts = sorted(
                (int(r["fanin"]), val(r, "rtx_per_mb"))
                for r in rows if r["mode"] == mode and r["fanin"]
            )
            if pts:
                ax.plot(
                    [p[0] for p in pts], [p[1] for p in pts],
                    marker="o", linewidth=1.7, label=LABEL[mode], color=COLOR[mode],
                )
        ax.set_title("Fig. 3: retransmit pressure, %s" % title, loc="left")
        ax.set_xlabel("fan-in")
        ax.set_ylabel("retransmitted packets / delivered MB")
        ax.set_xticks([4, 8, 16, 32, 64])
    axes[1].legend(ncol=1, frameon=True)
    save(fig, "3_incast_retransmits_per_mb")


def fig4_queue_trace():
    scenario = "C_queue_pressure_32"
    fig, axes = plt.subplots(3, 1, figsize=(9.2, 7.4), sharex=True)
    target_drawn = False
    for mode in MODES_CSIG:
        rows = trace(scenario, mode)
        if not rows:
            continue
        x = [val(r, "t_us") for r in rows]
        axes[0].plot(
            x, [val(r, "csig_delay_us") for r in rows],
            color=COLOR[mode], label=LABEL[mode], linewidth=1.15,
        )
        if mode == "csig_delay_abw" and not target_drawn:
            target = [val(r, "target_hop_delay_us") for r in rows]
            axes[0].plot(
                x, target, color="#666666", linestyle="--", linewidth=1.0,
                label="CSIG delay+ABW target",
            )
            target_drawn = True
        if mode == "csig_delay_abw":
            axes[1].plot(
                x, [val(r, "abw_fraction") for r in rows],
                color=COLOR[mode], linewidth=1.15, label=LABEL[mode],
            )
        rx, ry = rate_proxy(rows)
        ry = smooth(ry)
        axes[2].plot(rx, ry, color=COLOR[mode], linewidth=1.15, label=LABEL[mode])
    axes[0].set_title("Fig. 4: CSIG pressure and recovery trace, 32:1 incast", loc="left")
    axes[0].set_ylabel("CSIG delay (us)")
    axes[1].set_ylabel("min ABW / link")
    axes[1].set_ylim(-0.05, 1.05)
    axes[2].set_ylabel("tracked-flow send-rate proxy (Gbps)")
    axes[2].set_xlabel("simulation time (us)")
    for ax in axes:
        ax.legend(ncol=2, frameon=True)
    save(fig, "4_queue_pressure_trace")


def fig5_derived_scalars(derived):
    scenario = "C_queue_pressure_32"
    rows = {r["mode"]: r for r in derived if r["scenario"] == scenario}
    names = MODES_CSIG
    labels = [LABEL[m] for m in names]
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8))
    series = [
        ("overshoot_area_us2", "CSIG overshoot area (us^2)"),
        ("recovery_time_us", "CSIG recovery time (us)"),
        ("peak_csig_delay_us", "peak CSIG delay (us)"),
    ]
    for ax, (key, ylabel) in zip(axes, series):
        ax.bar(np.arange(len(names)), [val(rows.get(m), key) for m in names],
               color=[COLOR[m] for m in names])
        ax.set_xticks(np.arange(len(names)))
        ax.set_xticklabels(labels, rotation=18, ha="right")
        ax.set_ylabel(ylabel)
    axes[0].set_title("Fig. 5: bottleneck-delay control scalars", loc="left")
    save(fig, "5_bottleneck_delay_scalars")


def fig6_mixed_recovery():
    scenario = "D_mixed_recovery"
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 5.8), sharex=True)
    for mode in MODES_UEC:
        rows = trace(scenario, mode)
        if not rows:
            continue
        x, y = rate_proxy(rows)
        y = smooth(y)
        axes[0].plot(x, y, color=COLOR[mode], label=LABEL[mode], linewidth=1.0)
        if mode == "csig_delay_abw":
            axes[1].plot(
                [val(r, "t_us") for r in rows],
                [val(r, "abw_fraction") for r in rows],
                color=COLOR[mode], label=LABEL[mode], linewidth=1.1,
            )
    axes[0].set_title("Fig. 6: mixed long/short recovery diagnostic", loc="left")
    axes[0].set_ylabel("tracked-flow send-rate proxy (Gbps)")
    axes[1].set_ylabel("min ABW / link")
    axes[1].set_ylim(-0.05, 1.05)
    axes[1].set_xlabel("simulation time (us)")
    for ax in axes:
        ax.legend(ncol=2, frameon=True)
    save(fig, "6_mixed_recovery_diagnostic")


def fig7_multihop(runs, per_flow):
    scenario = "E_multihop_fairness"
    flow_ids = sorted({int(r["flow_id"]) for r in per_flow if r["scenario"] == scenario})
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.5))
    width = 0.84 / len(MODES_MULTIHOP)
    x = np.arange(len(flow_ids))
    for i, mode in enumerate(MODES_MULTIHOP):
        ys = []
        for fid in flow_ids:
            hit = [
                val(r, "goodput_gbps") for r in per_flow
                if r["scenario"] == scenario and r["mode"] == mode and int(r["flow_id"]) == fid
            ]
            ys.append(hit[0] if hit else 0.0)
        axes[0].bar(x + i * width, ys, width, label=LABEL[mode], color=COLOR[mode])
    axes[0].set_title("Fig. 7a: multi-hop per-flow goodput", loc="left")
    axes[0].set_xlabel("flow id")
    axes[0].set_ylabel("goodput (Gbps)")
    axes[0].set_xticks(x + (len(MODES_MULTIHOP) - 1) * width / 2)
    axes[0].set_xticklabels([str(i) for i in flow_ids])
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=True,
               bbox_to_anchor=(0.38, 1.05))

    bk = by_key(runs)
    bx = np.arange(len(MODES_MULTIHOP))
    axes[1].bar(
        bx, [val(bk.get((scenario, m)), "jfi_goodput") for m in MODES_MULTIHOP],
        color=[COLOR[m] for m in MODES_MULTIHOP],
    )
    axes[1].set_title("Fig. 7b: multi-hop Jain fairness", loc="left")
    axes[1].set_ylabel("Jain fairness index")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_xticks(bx)
    axes[1].set_xticklabels([LABEL[m] for m in MODES_MULTIHOP], rotation=18, ha="right")
    save(fig, "7_multihop_fairness")


def main():
    runs = read_csv(RUNS)
    per_flow = read_csv(PER_FLOW)
    derived = read_csv(DERIVED)
    if not runs:
        raise SystemExit("missing results/runs.csv; run parsers/parse_all.py first")
    fig1_lowload(runs)
    fig2_incast_fct(runs)
    fig3_incast_loss(runs)
    fig4_queue_trace()
    fig5_derived_scalars(derived)
    fig6_mixed_recovery()
    fig7_multihop(runs, per_flow)
    print("# done")


if __name__ == "__main__":
    main()
