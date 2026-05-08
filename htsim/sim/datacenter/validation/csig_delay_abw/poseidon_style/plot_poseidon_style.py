#!/usr/bin/env python3
"""Generate Poseidon-paper-style figures for the CSIG/NSCC project.

The plots intentionally live outside plots/figs_clean so the paper-style
diagnostics do not pollute the main CSIG delay+ABW figure set.
"""

import csv
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_DIR = os.path.dirname(HERE)
RESULTS_DIR = os.path.join(HARNESS_DIR, "results")
TRACES_DIR = os.path.join(RESULTS_DIR, "traces")
FIGS_DIR = os.path.join(HERE, "figs")

RUNS = os.path.join(RESULTS_DIR, "runs.csv")
PER_FLOW = os.path.join(RESULTS_DIR, "per_flow.csv")
DERIVED = os.path.join(RESULTS_DIR, "derived_metrics.csv")
SWEEP = os.path.join(RESULTS_DIR, "delay_abw_sweep.csv")
SUMMARY = os.path.join(HERE, "SUMMARY.md")

MODES = (
    "baseline_rtt",
    "hpcc",
    "csig_poseidon_rate",
    "csig_delay_abw",
)
UEC_TRACE_MODES = (
    "baseline_rtt",
    "csig_poseidon_rate",
    "csig_delay_abw",
)
CSIG_TRACE_MODES = (
    "csig_poseidon_rate",
    "csig_delay_abw",
)

LABEL = {
    "baseline_rtt": "NSCC (RTT)",
    "hpcc": "HPCC",
    "csig_poseidon_rate": "CSIG + Poseidon-rate",
    "csig_delay_abw": "CSIG delay + ABW",
}
COLOR = {
    "baseline_rtt": "#4D4D4D",
    "hpcc": "#E69F00",
    "csig_poseidon_rate": "#009E73",
    "csig_delay_abw": "#CC79A7",
}

plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "legend.fontsize": 7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.linestyle": ":",
    "grid.alpha": 0.38,
    "figure.dpi": 150,
    "savefig.dpi": 260,
})


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fp:
        return list(csv.DictReader(fp))


def f(row, key, default=0.0):
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


def smooth(vals, window=9):
    if len(vals) < window:
        return vals
    half = window // 2
    out = []
    for i in range(len(vals)):
        lo = max(0, i - half)
        hi = min(len(vals), i + half + 1)
        out.append(sum(vals[lo:hi]) / (hi - lo))
    return out


def t_ms(rows):
    return [f(r, "t_us") / 1000.0 for r in rows]


def rate_proxy(rows):
    x, y = [], []
    for r in rows:
        raw_rtt = f(r, "raw_rtt_us")
        if raw_rtt <= 0.1:
            continue
        x.append(f(r, "t_us") / 1000.0)
        y.append(f(r, "cwnd_after_bytes") * 8.0 / (raw_rtt * 1e-6) / 1e9)
    return x, smooth(y)


def mode_goodputs(per_flow, scenario, mode):
    rows = [
        r for r in per_flow
        if r["scenario"] == scenario and r["mode"] == mode
    ]
    rows.sort(key=lambda r: int(r["flow_id"]))
    return [int(r["flow_id"]) for r in rows], [f(r, "goodput_gbps") for r in rows]


def jfi(runs, scenario, mode):
    hit = [r for r in runs if r["scenario"] == scenario and r["mode"] == mode]
    return f(hit[0], "jfi_goodput") if hit else 0.0


def save(fig, name):
    os.makedirs(FIGS_DIR, exist_ok=True)
    png = os.path.join(FIGS_DIR, name + ".png")
    pdf = os.path.join(FIGS_DIR, name + ".pdf")
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    print("# wrote %s and %s" % (png, pdf))


def add_mode_legend(fig, ax, ncol=3, y=-0.01):
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=ncol,
                   bbox_to_anchor=(0.5, y), frameon=True)


def grouped_goodput_bars(ax, per_flow, scenario, modes=MODES, width_scale=0.84):
    flow_ids = sorted({
        int(r["flow_id"]) for r in per_flow
        if r["scenario"] == scenario and r["mode"] in modes
    })
    x = np.arange(len(flow_ids))
    width = width_scale / len(modes)
    for i, mode in enumerate(modes):
        _, vals = mode_goodputs(per_flow, scenario, mode)
        if not vals:
            vals = [0.0] * len(flow_ids)
        ax.bar(x + i * width, vals, width, color=COLOR[mode], label=LABEL[mode])
    ax.set_xticks(x + (len(modes) - 1) * width / 2)
    ax.set_xticklabels([str(i) for i in flow_ids])
    ax.set_xlabel("flow id")
    ax.set_ylabel("goodput (Gbps)")


def plot_rate_proxy(ax, scenario, modes=UEC_TRACE_MODES):
    for mode in modes:
        rows = trace(scenario, mode)
        if not rows:
            continue
        x, y = rate_proxy(rows)
        ax.plot(x, y, color=COLOR[mode], linewidth=1.15, label=LABEL[mode])
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("tracked-flow send-rate proxy (Gbps)")


def plot_delay_signals(ax, scenario):
    for mode in UEC_TRACE_MODES:
        rows = trace(scenario, mode)
        if not rows:
            continue
        x = t_ms(rows)
        if mode == "baseline_rtt":
            y = smooth([f(r, "rtt_delay_us_counterfactual") for r in rows])
            label = "NSCC RTT delay"
        else:
            y = smooth([f(r, "csig_delay_us") for r in rows])
            label = LABEL[mode]
        ax.plot(x, y, color=COLOR[mode], linewidth=1.1, label=label)
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("delay signal (us)")


def fig14_multihop(runs, per_flow):
    scenario = "E_multihop_fairness"
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.0))
    axes = axes.ravel()

    grouped_goodput_bars(axes[0], per_flow, scenario)
    axes[0].set_title("(a) All-flow goodput distribution")

    plot_rate_proxy(axes[1], scenario)
    axes[1].set_title("(b) Tracked flow: rate proxy")

    plot_delay_signals(axes[2], scenario)
    axes[2].set_title("(c) RTT path delay vs CSIG max-hop delay")

    rows_p = trace(scenario, "csig_poseidon_rate")
    rows_d = trace(scenario, "csig_delay_abw")
    if rows_p:
        axes[3].plot(t_ms(rows_p), smooth([f(r, "csig_delay_us") for r in rows_p]),
                     color=COLOR["csig_poseidon_rate"], label="Poseidon-rate MPD")
        axes[3].plot(t_ms(rows_p), smooth([f(r, "effective_target_us") for r in rows_p]),
                     color=COLOR["csig_poseidon_rate"], linestyle="--",
                     label="Poseidon-rate target")
    if rows_d:
        axes[3].plot(t_ms(rows_d), smooth([f(r, "csig_delay_us") for r in rows_d]),
                     color=COLOR["csig_delay_abw"], label="CSIG delay+ABW delay")
        axes[3].plot(t_ms(rows_d), smooth([f(r, "target_hop_delay_us") for r in rows_d]),
                     color=COLOR["csig_delay_abw"], linestyle="--", label="CSIG delay+ABW target")
    axes[3].set_title("(d) Target vs bottleneck delay")
    axes[3].set_xlabel("time (ms)")
    axes[3].set_ylabel("delay / target (us)")

    add_mode_legend(fig, axes[0], ncol=5, y=0.005)
    for ax in axes[1:]:
        ax.legend(frameon=True)
    fig.suptitle("Poseidon Fig. 14-style: multi-hop congestion, htsim CSIG modes", y=0.99)
    fig.tight_layout(rect=[0, 0.06, 1, 0.95], h_pad=1.5, w_pad=1.5)
    save(fig, "fig14_multihop_congestion_like")


def fig15_reverse_path(per_flow):
    scenario = "F_reverse_path"
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 3.9))

    grouped_goodput_bars(axes[0], per_flow, scenario)
    axes[0].set_title("(a) All-flow goodput")

    plot_rate_proxy(axes[1], scenario)
    axes[1].set_title("(b) Tracked flow: rate proxy")

    plot_delay_signals(axes[2], scenario)
    axes[2].set_title("(c) Tracked flow: delay signal")

    add_mode_legend(fig, axes[0], ncol=5, y=0.0)
    for ax in axes[1:]:
        ax.legend(frameon=True)
    fig.suptitle("Poseidon Fig. 15-style: reverse-path/audit case", y=0.99)
    fig.tight_layout(rect=[0, 0.12, 1, 0.94], w_pad=1.5)
    save(fig, "fig15_reverse_path_like")


def fig16_single_bottleneck(runs, per_flow):
    scenario = "C_queue_pressure_32"
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0))
    grouped_goodput_bars(axes[0], per_flow, scenario)
    axes[0].set_title("(a) 32:1 queue-pressure per-flow goodput")

    bx = np.arange(len(MODES))
    axes[1].bar(bx, [jfi(runs, scenario, m) for m in MODES],
                color=[COLOR[m] for m in MODES])
    axes[1].set_xticks(bx)
    axes[1].set_xticklabels([LABEL[m] for m in MODES], rotation=18, ha="right")
    axes[1].set_ylim(0.85, 1.01)
    axes[1].set_ylabel("Jain fairness index")
    axes[1].set_title("(b) Aggregate fairness, not selected flows")

    add_mode_legend(fig, axes[0], ncol=5, y=0.0)
    fig.suptitle("Poseidon Fig. 16-style: single-bottleneck fairness equivalent", y=0.99)
    fig.tight_layout(rect=[0, 0.14, 1, 0.94], w_pad=1.5)
    save(fig, "fig16_single_bottleneck_fairness_like")


def fig17_convergence_stability():
    scenario = "D_mixed_recovery"
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.0))

    plot_rate_proxy(axes[0], scenario)
    axes[0].set_title("(a) Recovery/ramp behavior")

    cvs = []
    labels = []
    for mode in UEC_TRACE_MODES:
        rows = trace(scenario, mode)
        if not rows:
            continue
        x, y = rate_proxy(rows)
        steady = [v for t, v in zip(x, y) if t >= 0.9]
        if len(steady) < 3:
            steady = y
        mean = sum(steady) / len(steady) if steady else 0.0
        std = math.sqrt(sum((v - mean) ** 2 for v in steady) / len(steady)) if steady else 0.0
        cvs.append(std / mean if mean > 0 else 0.0)
        labels.append(LABEL[mode])
    axes[1].bar(np.arange(len(cvs)), cvs, color=[COLOR[m] for m in UEC_TRACE_MODES])
    axes[1].set_xticks(np.arange(len(cvs)))
    axes[1].set_xticklabels(labels, rotation=18, ha="right")
    axes[1].set_ylabel("coefficient of variation")
    axes[1].set_title("(b) Stability of tracked-flow proxy")

    axes[0].legend(frameon=True)
    fig.suptitle("Poseidon Fig. 17-style: convergence and stability", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94], w_pad=1.5)
    save(fig, "fig17_convergence_stability_like")


def p99(vals):
    if not vals:
        return 0.0
    vals = sorted(vals)
    idx = min(len(vals) - 1, int(round(0.99 * (len(vals) - 1))))
    return vals[idx]


def fig18_rtt_delay_stability():
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.0))
    scenarios = [("C_queue_pressure_32", "queue pressure"), ("D_mixed_recovery", "mixed recovery")]
    for ax, (scenario, title) in zip(axes, scenarios):
        modes = UEC_TRACE_MODES
        vals = []
        for mode in modes:
            rows = trace(scenario, mode)
            vals.append(p99([f(r, "rtt_delay_us_counterfactual") for r in rows]))
        ax.bar(np.arange(len(modes)), vals, color=[COLOR[m] for m in modes])
        ax.set_xticks(np.arange(len(modes)))
        ax.set_xticklabels([LABEL[m] for m in modes], rotation=18, ha="right")
        ax.set_ylabel("tracked-flow p99 RTT-delay counterfactual (us)")
        ax.set_title(title)
    fig.suptitle("Poseidon Fig. 18-style: RTT/delay stability", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94], w_pad=1.5)
    save(fig, "fig18_rtt_delay_stability_like")


def fig19_fct_latency(runs):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
    for ax, size, title in zip(axes, (256000, 1000000), ("256KB incast", "1MB incast")):
        for mode in MODES:
            pts = sorted(
                (int(r["fanin"]), f(r, "fct_us_max"))
                for r in runs
                if r["mode"] == mode
                and r["scenario"].startswith("B_incast_")
                and str(r["msg_bytes"]) == str(size)
                and r["fanin"]
            )
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        marker="o", linewidth=1.4, color=COLOR[mode],
                        label=LABEL[mode])
        ax.set_xticks([4, 8, 16, 32, 64])
        ax.set_xlabel("fan-in")
        ax.set_ylabel("request completion time (us)")
        ax.set_title(title)
    axes[1].legend(frameon=True)
    fig.suptitle("Poseidon Fig. 19-style: FCT/op-latency equivalent", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94], w_pad=1.5)
    save(fig, "fig19_fct_latency_like")


def fig21_sensitivity(sweep):
    rows = [
        r for r in sweep
        if r["target_divisor"] == "2.0" and r["delay_low_frac"] == "0.75"
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 6.4), sharex=True)
    for col, scenario in enumerate(("C_queue_pressure_32", "D_mixed_recovery")):
        rs = sorted([r for r in rows if r["scenario"] == scenario], key=lambda r: f(r, "gain"))
        x = [f(r, "gain") for r in rs]
        axes[0][col].plot(x, [f(r, "fct_us_max") for r in rs], marker="o", color=COLOR["csig_delay_abw"])
        axes[0][col].set_xscale("log", base=2)
        axes[0][col].set_title(scenario)
        axes[0][col].set_ylabel("max FCT (us)")
        axes[1][col].plot(x, [f(r, "pkts_rtx") for r in rs], marker="o", color=COLOR["csig_delay_abw"])
        axes[1][col].set_xscale("log", base=2)
        axes[1][col].set_xlabel("ABW gain")
        axes[1][col].set_ylabel("UEC retransmits")
    fig.suptitle("Poseidon Fig. 21-style: CSIG delay+ABW sensitivity", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94], h_pad=1.5, w_pad=1.5)
    save(fig, "fig21_sensitivity_like")


def write_summary(runs, derived):
    by = by_key(runs)
    lines = [
        "# Poseidon-Style Figure Summary",
        "",
        "## Key numbers",
        "",
    ]
    for sc in ("C_queue_pressure_32", "D_mixed_recovery", "E_multihop_fairness", "F_reverse_path"):
        lines.append("### `%s`" % sc)
        for mode in MODES:
            r = by.get((sc, mode))
            if not r:
                continue
            lines.append("- `%s`: maxFCT %.1fus, JFI %.4f, rtx %s" % (
                mode, f(r, "fct_us_max"), f(r, "jfi_goodput"), r.get("pkts_rtx", ""),
            ))
        lines.append("")
    lines += [
        "## Figure mapping",
        "",
        "- `fig14_multihop_congestion_like`: Poseidon Fig. 14-style multi-hop fairness and delay-target behavior.",
        "- `fig15_reverse_path_like`: Poseidon Fig. 15-style reverse-path/audit behavior.",
        "- `fig16_single_bottleneck_fairness_like`: Poseidon Fig. 16-style single-bottleneck fairness equivalent.",
        "- `fig17_convergence_stability_like`: Poseidon Fig. 17-style convergence/stability check.",
        "- `fig18_rtt_delay_stability_like`: Poseidon Fig. 18-style RTT/delay stability check.",
        "- `fig19_fct_latency_like`: Poseidon Fig. 19-style FCT/op-latency sweep.",
        "- `fig21_sensitivity_like`: Poseidon Fig. 21-style sensitivity study.",
        "",
    ]
    with open(SUMMARY, "w") as fp:
        fp.write("\n".join(lines))
    print("# wrote %s" % SUMMARY)


def main():
    runs = read_csv(RUNS)
    per_flow = read_csv(PER_FLOW)
    derived = read_csv(DERIVED)
    sweep = read_csv(SWEEP)
    if not runs or not per_flow:
        raise SystemExit("missing results/runs.csv or results/per_flow.csv")

    fig14_multihop(runs, per_flow)
    fig15_reverse_path(per_flow)
    fig16_single_bottleneck(runs, per_flow)
    fig17_convergence_stability()
    fig18_rtt_delay_stability()
    fig19_fct_latency(runs)
    if sweep:
        fig21_sensitivity(sweep)
    write_summary(runs, derived)
    print("# done")


if __name__ == "__main__":
    main()
