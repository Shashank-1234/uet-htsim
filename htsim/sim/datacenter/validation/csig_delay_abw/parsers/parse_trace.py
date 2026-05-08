#!/usr/bin/env python3
"""Parse CSIG_TRACE rows from one raw trace run into CSV."""

import csv
import os
import re
import sys

TRACE_RE = re.compile(r"^CSIG_TRACE\s+(.+)$")
KV_RE = re.compile(r"(\w+)=([^\s]+)")

FIELDS = [
    "t_us", "flow", "ack_type",
    "cwnd_before_bytes", "cwnd_after_bytes", "in_flight_bytes",
    "raw_rtt_us", "rtt_delay_us_counterfactual",
    "control_delay_us_used", "ecn_echo",
    "csig_delay_us",
    "csig_abw_valid", "csig_abw_encoded", "csig_abw_bps",
    "abw_fraction", "abw_budget_bytes", "abw_delta_bytes",
    "acked_psn", "newly_acked_bytes", "nscc_branch",
    "effective_target_us", "target_hop_delay_us", "control_mode",
    "poseidon_mpd_us", "poseidon_mpt_us",
    "poseidon_raw_update_ratio", "poseidon_applied_update_ratio",
    "poseidon_m", "poseidon_mpd_bytes", "poseidon_mpt_bytes",
    "poseidon_rate_bps", "poseidon_rate_before_bps", "poseidon_rate_after_bps",
    "poseidon_cwnd_pkts", "poseidon_loss_event",
]


def parse_one(path):
    rows = []
    with open(path) as fp:
        for line in fp:
            m = TRACE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            kv = dict(KV_RE.findall(m.group(1)))
            rows.append([kv.get(k, "") for k in FIELDS])
    return rows


def write_csv(rows, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(FIELDS)
        writer.writerows(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: parse_trace.py <raw.trace.out> <out.csv>")
    rows_ = parse_one(sys.argv[1])
    write_csv(rows_, sys.argv[2])
    print("# wrote %d rows to %s" % (len(rows_), sys.argv[2]))
