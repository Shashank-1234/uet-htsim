#!/usr/bin/env python3
"""Sweep CSIG delay+ABW recovery knobs on the two attribution scenarios.

This deliberately writes to results/sweep_raw and results/delay_abw_sweep.csv
so the main matrix remains stable.
"""

import csv
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_DIR = os.path.dirname(HERE)
RAW_DIR = os.path.join(HARNESS_DIR, "results", "sweep_raw")
OUT_CSV = os.path.join(HARNESS_DIR, "results", "delay_abw_sweep.csv")
RUN_ONE = os.path.join(HERE, "run_one.sh")
PARSERS = os.path.join(HARNESS_DIR, "parsers")
sys.path.insert(0, PARSERS)
from parse_run import aggregate, parse  # noqa: E402

SCENARIOS = (
    ("C_queue_pressure_32", "cm/C_queue_pressure_32_1MB.cm", "-end 100000"),
    ("D_mixed_recovery", "cm/D_mixed_recovery.cm", "-end 200000"),
)
GAINS = (0.0625, 0.125, 0.25, 0.5, 1.0)
LOW_FRACS = (0.5, 0.75, 1.0)
DIVISORS = (2.0, 3.0, 4.0)

FIELDS = (
    "scenario", "gain", "delay_low_frac", "target_divisor",
    "fct_us_max", "fct_us_p99", "jfi_goodput", "pkts_rtx", "pkts_nacks",
    "rtx_per_mb", "multi_dec_total", "fast_inc_total", "wallclock_s",
)


def run_one(sc_id, cm_rel, extra, gain, low_frac, divisor):
    tag = "g%s_f%s_k%s" % (
        str(gain).replace(".", "p"),
        str(low_frac).replace(".", "p"),
        str(divisor).replace(".", "p"),
    )
    out = os.path.join(RAW_DIR, "%s__csig_delay_abw__%s.out" % (sc_id, tag))
    cm = os.path.join(HARNESS_DIR, cm_rel)
    env = os.environ.copy()
    env["CSIG_DELAY_ABW_GAIN"] = str(gain)
    env["CSIG_DELAY_ABW_LOW_FRAC"] = str(low_frac)
    env["CSIG_DELAY_ABW_TARGET_DIVISOR"] = str(divisor)
    cmd = [RUN_ONE, cm, "csig_delay_abw", out] + extra.split()
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        return {
            "scenario": sc_id, "gain": gain, "delay_low_frac": low_frac,
            "target_divisor": divisor, "error": (proc.stdout + proc.stderr)[-1200:],
        }
    flows, summary, linkspeed, wallclock = parse(out, cm)
    agg = aggregate(flows, summary, linkspeed, wallclock)
    return {
        "scenario": sc_id,
        "gain": gain,
        "delay_low_frac": low_frac,
        "target_divisor": divisor,
        **agg,
    }


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    tasks = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for sc_id, cm, extra in SCENARIOS:
            for gain in GAINS:
                for low_frac in LOW_FRACS:
                    for divisor in DIVISORS:
                        tasks.append(pool.submit(run_one, sc_id, cm, extra, gain, low_frac, divisor))

        rows = []
        for fut in as_completed(tasks):
            row = fut.result()
            rows.append(row)
            if "error" in row:
                print("[FAIL] %(scenario)s gain=%(gain)s low=%(delay_low_frac)s div=%(target_divisor)s" % row)
            else:
                print("[OK ] %(scenario)s gain=%(gain)s low=%(delay_low_frac)s div=%(target_divisor)s "
                      "max=%(fct_us_max).1f rtx=%(pkts_rtx)s" % row)

    rows.sort(key=lambda r: (
        r["scenario"], float(r["target_divisor"]), float(r["delay_low_frac"]), float(r["gain"])
    ))
    with open(OUT_CSV, "w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            if "error" not in row:
                writer.writerow({k: row.get(k, "") for k in FIELDS})
    print("# wrote %s (%d successful rows)" % (OUT_CSV, sum(1 for r in rows if "error" not in r)))


if __name__ == "__main__":
    main()
