#!/usr/bin/env python3
"""Parse one raw htsim output into aggregate and per-flow metrics."""

import os
import re
import sys

LINKSPEED_RE = re.compile(r"^Linkspeed set to (\d+)Gbps")
HPCC_RATE_RE = re.compile(r"^Initial CWND is \d+ target RTT .* rate (\d+)")
FLOW_RE = re.compile(
    r"^Flow (\S+) flowId (\d+) uecSrc (\d+) "
    r"finished at ([0-9.]+) "
    r"total messages (\d+) total packets (\d+) RTS (\d+) total bytes (\d+) "
    r"in_flight now (\-?\d+) "
    r"fair_inc (\-?\d+) prop_inc (\-?\d+) fast_inc (\-?\d+) eta_inc (\-?\d+) "
    r"multi_dec -(\-?\d+) quick_dec -(\-?\d+) nack_dec -(\-?\d+)"
)
HPCC_FLOW_RE = re.compile(r"^Flow (HPCC_(\d+)_(\d+)) finished at ([0-9.]+) total bytes (\d+)")
SUMMARY_RE = re.compile(
    r"^New: (\d+) Rtx: (\d+) RTS: (\d+) Bounced: (\d+) ACKs: (\d+) NACKs: (\d+)"
)
HPCC_SUMMARY_RE = re.compile(r"^New: (\d+) Rtx: (\d+)")
WALLCLOCK_RE = re.compile(r"^# wallclock_seconds (\d+)")


def parse_cm(path):
    flows = {}
    if not path or not os.path.exists(path):
        return flows
    flow_re = re.compile(r"^(\d+)->(\d+)\s+id\s+(\d+)\s+start\s+(\d+)\s+size\s+(\d+)")
    with open(path) as fp:
        for line in fp:
            m = flow_re.match(line.strip())
            if not m:
                continue
            src, dst, fid, start, size = map(int, m.groups())
            flows[fid] = {
                "src": src,
                "dst": dst,
                "start_us": start,
                "declared_size_bytes": size,
            }
    return flows


def parse(path, cm_path=None):
    cm = parse_cm(cm_path)
    flows = []
    summary = {}
    linkspeed_gbps = 100
    wallclock = 0
    hpcc_flow_id = 0
    with open(path) as fp:
        for line in fp:
            m = LINKSPEED_RE.match(line)
            if m:
                linkspeed_gbps = int(m.group(1))
                continue
            m = HPCC_RATE_RE.match(line)
            if m:
                linkspeed_gbps = int(round(int(m.group(1)) / 1e9))
                continue
            m = FLOW_RE.match(line)
            if m:
                fid = int(m.group(2))
                fct_us = float(m.group(4))
                bytes_ = int(m.group(8))
                meta = cm.get(fid, {})
                flows.append({
                    "name": m.group(1),
                    "flow_id": fid,
                    "src": int(m.group(3)),
                    "dst": meta.get("dst", -1),
                    "start_us": meta.get("start_us", -1),
                    "declared_size_bytes": meta.get("declared_size_bytes", -1),
                    "fct_us": fct_us,
                    "total_pkts": int(m.group(6)),
                    "total_bytes": bytes_,
                    "fair_inc": int(m.group(10)),
                    "prop_inc": int(m.group(11)),
                    "fast_inc": int(m.group(12)),
                    "eta_inc": int(m.group(13)),
                    "multi_dec": int(m.group(14)),
                    "quick_dec": int(m.group(15)),
                    "nack_dec": int(m.group(16)),
                    "goodput_gbps": (bytes_ * 8) / (fct_us * 1e-6) / 1e9 if fct_us > 0 else 0.0,
                })
                continue
            m = HPCC_FLOW_RE.match(line)
            if m:
                hpcc_flow_id += 1
                fid = hpcc_flow_id
                fct_us = float(m.group(4))
                bytes_ = int(m.group(5))
                meta = cm.get(fid, {})
                flows.append({
                    "name": m.group(1),
                    "flow_id": fid,
                    "src": int(m.group(2)),
                    "dst": int(m.group(3)),
                    "start_us": meta.get("start_us", -1),
                    "declared_size_bytes": meta.get("declared_size_bytes", -1),
                    "fct_us": fct_us,
                    "total_pkts": int((bytes_ + 8999) / 9000),
                    "total_bytes": bytes_,
                    "fair_inc": 0, "prop_inc": 0, "fast_inc": 0,
                    "eta_inc": 0, "multi_dec": 0, "quick_dec": 0, "nack_dec": 0,
                    "goodput_gbps": (bytes_ * 8) / (fct_us * 1e-6) / 1e9 if fct_us > 0 else 0.0,
                })
                continue
            m = SUMMARY_RE.match(line)
            if m:
                summary = {
                    "new_pkts": int(m.group(1)),
                    "pkts_rtx": int(m.group(2)),
                    "rts": int(m.group(3)),
                    "bounced": int(m.group(4)),
                    "acks": int(m.group(5)),
                    "nacks": int(m.group(6)),
                }
                continue
            m = HPCC_SUMMARY_RE.match(line)
            if m:
                summary = {
                    "new_pkts": int(m.group(1)),
                    "pkts_rtx": int(m.group(2)),
                    "rts": 0, "bounced": 0, "acks": 0, "nacks": 0,
                }
                continue
            m = WALLCLOCK_RE.match(line)
            if m:
                wallclock = int(m.group(1))
    return flows, summary, linkspeed_gbps, wallclock


def jain(values):
    if not values:
        return 0.0
    s = sum(values)
    sq = sum(v * v for v in values)
    return (s * s) / (len(values) * sq) if sq else 1.0


def percentile(values, p):
    if not values:
        return 0.0
    vals = sorted(values)
    k = max(0, min(len(vals) - 1, int(round((p / 100.0) * (len(vals) - 1)))))
    return vals[k]


def aggregate(flows, summary, linkspeed_gbps, wallclock):
    if not flows:
        return None
    fcts = [f["fct_us"] for f in flows]
    gps = [f["goodput_gbps"] for f in flows]
    delivered_bytes = sum(f["total_bytes"] for f in flows)
    delivered_mb = delivered_bytes / 1_000_000.0
    pkts_rtx = summary.get("pkts_rtx", 0)
    return {
        "n_flows": len(flows),
        "linkspeed_gbps": linkspeed_gbps,
        "fct_us_max": max(fcts),
        "fct_us_p99": percentile(fcts, 99),
        "fct_us_min": min(fcts),
        "fct_us_mean": sum(fcts) / len(fcts),
        "goodput_gbps_max": max(gps),
        "goodput_gbps_min": min(gps),
        "goodput_gbps_mean": sum(gps) / len(gps),
        "jfi_goodput": jain(gps),
        "pkts_new": summary.get("new_pkts", 0),
        "pkts_rtx": pkts_rtx,
        "pkts_nacks": summary.get("nacks", 0),
        "delivered_mb": delivered_mb,
        "rtx_per_mb": pkts_rtx / delivered_mb if delivered_mb > 0 else 0.0,
        "wallclock_s": wallclock,
        "multi_dec_total": sum(f["multi_dec"] for f in flows),
        "fair_inc_total": sum(f["fair_inc"] for f in flows),
        "prop_inc_total": sum(f["prop_inc"] for f in flows),
        "fast_inc_total": sum(f["fast_inc"] for f in flows),
        "eta_inc_total": sum(f["eta_inc"] for f in flows),
    }


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: parse_run.py <raw.out> [cm]")
    flows_, summary_, ls_, wc_ = parse(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
    print(aggregate(flows_, summary_, ls_, wc_))
