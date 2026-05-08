#!/usr/bin/env python3
"""Run the focused CSIG delay+ABW scenario matrix."""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_DIR = os.path.dirname(HERE)
RAW_DIR = os.path.join(HARNESS_DIR, "results", "raw")
RUN_ONE = os.path.join(HERE, "run_one.sh")

MODES = (
    "baseline_rtt",
    "hpcc",
    "csig_poseidon_rate",
    "csig_delay_abw",       # full proposal: CSIG decrease + ABW-gated recovery
)

SCENARIOS = (
    {"id": "A1_lowload_1f",        "cm": "cm/A1_lowload_1f.cm",        "extra": "-end 10000",  "trace": False},
    {"id": "A2_lowload_4f",        "cm": "cm/A2_lowload_4f.cm",        "extra": "-end 10000",  "trace": False},
    {"id": "B_incast_4_256K",      "cm": "cm/B_incast_4_256K.cm",      "extra": "-end 100000", "trace": False},
    {"id": "B_incast_8_256K",      "cm": "cm/B_incast_8.cm",           "extra": "-end 100000", "trace": False},
    {"id": "B_incast_16_256K",     "cm": "cm/B_incast_16.cm",          "extra": "-end 100000", "trace": False},
    {"id": "B_incast_32_256K",     "cm": "cm/B_incast_32.cm",          "extra": "-end 100000", "trace": False},
    {"id": "B_incast_64_256K",     "cm": "cm/B_incast_64_256K.cm",     "extra": "-end 100000", "trace": False},
    {"id": "B_incast_4_1MB",       "cm": "cm/B_incast_4_1MB.cm",       "extra": "-end 100000", "trace": False},
    {"id": "B_incast_8_1MB",       "cm": "cm/B_incast_8_1MB.cm",       "extra": "-end 100000", "trace": False},
    {"id": "B_incast_16_1MB",      "cm": "cm/B_incast_16_1MB.cm",      "extra": "-end 100000", "trace": False},
    {"id": "B_incast_32_1MB",      "cm": "cm/B_incast_32_1MB.cm",      "extra": "-end 100000", "trace": False},
    {"id": "B_incast_64_1MB",      "cm": "cm/B_incast_64_1MB.cm",      "extra": "-end 100000", "trace": False},
    {"id": "C_queue_pressure_32",  "cm": "cm/C_queue_pressure_32_1MB.cm", "extra": "-end 100000", "trace": True},
    {"id": "D_mixed_recovery",     "cm": "cm/D_mixed_recovery.cm",     "extra": "-end 200000", "trace": True},
    {"id": "E_multihop_fairness",  "cm": "cm/E_multihop_fairness.cm",  "extra": "-end 100000", "trace": True},
    {"id": "F_reverse_path",       "cm": "cm/F_reverse_path.cm",       "extra": "-end 100000", "trace": True},
)


def run_cell(sc, mode, trace):
    suffix = ".trace.out" if trace and mode != "hpcc" else ".out"
    out = os.path.join(RAW_DIR, "%s__%s%s" % (sc["id"], mode, suffix))
    cm = os.path.normpath(os.path.join(HARNESS_DIR, sc["cm"]))
    extra = sc.get("extra", "").split()
    if trace and mode != "hpcc":
        extra += ["-debug_flowid", "1", "-csig_trace"]
    cmd = [RUN_ONE, cm, mode, out] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return sc["id"], mode, out, proc.returncode, proc.stdout, proc.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", action="store_true",
                    help="run only trace-marked scenarios with CSIG trace output")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--modes", default=",".join(MODES),
                    help="comma-separated mode subset")
    args = ap.parse_args()

    modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
    bad = [m for m in modes if m not in MODES]
    if bad:
        sys.exit("unknown modes: %s" % ", ".join(bad))

    os.makedirs(RAW_DIR, exist_ok=True)
    scenarios = [s for s in SCENARIOS if (s["trace"] if args.trace else True)]

    futures = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for sc in scenarios:
            for mode in modes:
                futures.append(pool.submit(run_cell, sc, mode, args.trace))

        ok = 0
        for fut in as_completed(futures):
            sid, mode, out, rc, stdout, stderr = fut.result()
            tag = "OK " if rc == 0 else "FAIL"
            print("[%s] %-24s %-20s rc=%d %s" % (tag, sid, mode, rc, out))
            if rc == 0:
                ok += 1
            else:
                if stdout:
                    sys.stderr.write(stdout[-1200:] + "\n")
                if stderr:
                    sys.stderr.write(stderr[-1200:] + "\n")

    print("# %d/%d cells succeeded" % (ok, len(futures)))
    if ok != len(futures):
        sys.exit(1)


if __name__ == "__main__":
    main()
