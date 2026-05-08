#!/bin/bash
# Run one (connection matrix, mode) cell for the CSIG delay+ABW harness.
#
# Usage:
#   run_one.sh <cm_path> <mode> <out_path> [extra htsim args...]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

if [[ $# -lt 3 ]]; then
    echo "Usage: $0 <cm_path> <mode> <out_path> [extra_args...]" >&2
    exit 2
fi

CM="$1"; MODE="$2"; OUT="$3"; shift 3

case "$MODE" in
    baseline_rtt)            FLAGS=() ;;
    hpcc)                    FLAGS=() ;;
    csig_poseidon_rate)      FLAGS=(-nscc_csig_poseidon_rate) ;;
    csig_delay_abw)          FLAGS=(-nscc_csig_delay_abw) ;;
    *) echo "FATAL: unknown mode '$MODE'" >&2; exit 2 ;;
esac

DELAY_ABW_FLAGS=()
if [[ "$MODE" == "csig_delay_abw" ]]; then
    # Harness defaults are the sweep-selected balanced setting. Simulator
    # defaults remain conservative; override here so validation is explicit.
    DELAY_ABW_FLAGS+=(-csig_delay_abw_target_divisor "${CSIG_DELAY_ABW_TARGET_DIVISOR:-2.0}")
    DELAY_ABW_FLAGS+=(-csig_delay_abw_gain "${CSIG_DELAY_ABW_GAIN:-0.125}")
    DELAY_ABW_FLAGS+=(-csig_delay_abw_low_frac "${CSIG_DELAY_ABW_LOW_FRAC:-0.75}")
fi

if [[ ! -f "$CM" ]]; then
    echo "FATAL: CM not found: $CM" >&2
    exit 2
fi
CM="$(cd "$(dirname "$CM")" && pwd)/$(basename "$CM")"

mkdir -p "$(dirname "$OUT")"
LOGOUT="${OUT%.out}.logout.dat"
LOGOUT="$(cd "$(dirname "$LOGOUT")" && pwd)/$(basename "$LOGOUT")"

START_TS=$(date +%s)
if [[ "$MODE" == "hpcc" ]]; then
    NODES="$(awk '/^Nodes[[:space:]]+/ { print $2; exit }' "$CM")"
    if [[ -z "$NODES" ]]; then
        echo "FATAL: could not read node count from $CM" >&2
        exit 2
    fi
    ( cd "$SIM_DC_DIR" && "$HTSIM_HPCC" -o "$LOGOUT" -nodes "$NODES" \
        -tm "$CM" -strat ecmp_host -paths 4 "$@" ) >"$OUT" 2>&1
    echo "# cmd htsim_hpcc -o $LOGOUT -nodes $NODES -tm $CM -strat ecmp_host -paths 4 $*" >> "$OUT"
else
    ( cd "$SIM_DC_DIR" && "$HTSIM_UEC" -o "$LOGOUT" -tm "$CM" \
        ${FLAGS[@]+"${FLAGS[@]}"} \
        ${DELAY_ABW_FLAGS[@]+"${DELAY_ABW_FLAGS[@]}"} \
        "$@" ) >"$OUT" 2>&1
    echo "# cmd htsim_uec -o $LOGOUT -tm $CM ${FLAGS[*]+${FLAGS[*]}} ${DELAY_ABW_FLAGS[*]+${DELAY_ABW_FLAGS[*]}} $*" >> "$OUT"
fi
END_TS=$(date +%s)
echo "# wallclock_seconds $((END_TS - START_TS))" >> "$OUT"
