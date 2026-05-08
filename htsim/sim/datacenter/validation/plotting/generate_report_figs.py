#!/usr/bin/env python3
"""Generate the selected report figures from the CSIG delay+ABW outputs."""

import argparse
import importlib.util
import os
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATION_DIR = os.path.dirname(HERE)
CSIG_DIR = os.path.join(VALIDATION_DIR, "csig_delay_abw")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def png_only_saver(plt, out_dir):
    def save(fig, name):
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, name + ".png")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        print("# wrote %s" % path)
    return save


def generate(out_dir):
    plot_all = load_module(
        "csig_delay_abw_plot_all",
        os.path.join(CSIG_DIR, "plots", "plot_all.py"),
    )

    os.makedirs(out_dir, exist_ok=True)

    plot_all.FIGS_DIR = out_dir
    plot_all.save = png_only_saver(plot_all.plt, out_dir)
    runs = plot_all.read_csv(plot_all.RUNS)
    per_flow = plot_all.read_csv(plot_all.PER_FLOW)
    if not runs:
        raise SystemExit("missing csig_delay_abw/results/runs.csv; run parsers/parse_all.py first")
    if not per_flow:
        raise SystemExit("missing csig_delay_abw/results/per_flow.csv; run parsers/parse_all.py first")

    plot_all.fig2_incast_fct(runs)
    plot_all.fig7_multihop(runs, per_flow)

    plot_clean = load_module(
        "csig_delay_abw_plot_clean",
        os.path.join(CSIG_DIR, "clean_poseidon_eval", "plot_clean.py"),
    )
    plot_clean.FIGS_DIR = out_dir
    plot_clean.save = png_only_saver(plot_clean.plt, out_dir)
    if not os.path.isdir(plot_clean.RAW_DIR):
        raise SystemExit("missing csig_delay_abw/poseidon_style/raw")

    plot_clean.fig21a_ablation()
    plot_clean.fig17_concurrency()

    tracked_flow = 1
    rows = []
    rows.extend(plot_clean.summarize_stage_metrics(
        scenario="paper14_multihop_mn",
        modes=plot_clean.MAIN_MODES,
        windows=plot_clean.stage_windows_mn(),
        tracked_flow_default=tracked_flow,
    ))
    rows.extend(plot_clean.summarize_stage_metrics(
        scenario="paper17_high_concurrency",
        modes=plot_clean.MAIN_MODES,
        windows=plot_clean.stage_windows_hc(),
        tracked_flow_default=tracked_flow,
    ))
    plot_clean.write_metrics_csv(rows, os.path.join(out_dir, "metrics_summary.csv"))


def main():
    parser = argparse.ArgumentParser(
        description="Generate only the selected report artifacts.",
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join(HERE, "figs"),
        help="output directory; default: plotting/figs",
    )
    args = parser.parse_args()
    generate(os.path.abspath(args.out_dir))


if __name__ == "__main__":
    main()
