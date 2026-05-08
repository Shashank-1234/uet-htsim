#!/bin/bash
# Shared paths for the CSIG delay+ABW harness.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_DC_DIR="$(cd "$HARNESS_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SIM_DC_DIR/../../.." && pwd)"

VENV_PY="$REPO_ROOT/.venv/bin/python"
HTSIM_UEC="$SIM_DC_DIR/htsim_uec"
HTSIM_HPCC="$SIM_DC_DIR/htsim_hpcc"

CM_DIR="$HARNESS_DIR/cm"
SCRIPTS_DIR="$HARNESS_DIR/scripts"
PARSERS_DIR="$HARNESS_DIR/parsers"
PLOTS_DIR="$HARNESS_DIR/plots"
RESULTS_DIR="$HARNESS_DIR/results"
RAW_DIR="$RESULTS_DIR/raw"
TRACES_DIR="$RESULTS_DIR/traces"

export HARNESS_DIR SIM_DC_DIR REPO_ROOT VENV_PY HTSIM_UEC HTSIM_HPCC \
       CM_DIR SCRIPTS_DIR PARSERS_DIR PLOTS_DIR RESULTS_DIR RAW_DIR TRACES_DIR

if [[ ! -x "$VENV_PY" ]]; then
    echo "FATAL: venv python not executable: $VENV_PY" >&2
    exit 2
fi
if [[ ! -x "$HTSIM_UEC" ]]; then
    echo "FATAL: htsim_uec not built: $HTSIM_UEC" >&2
    exit 2
fi
if [[ ! -x "$HTSIM_HPCC" ]]; then
    echo "WARN: htsim_hpcc not built: $HTSIM_HPCC; HPCC mode unavailable" >&2
fi
