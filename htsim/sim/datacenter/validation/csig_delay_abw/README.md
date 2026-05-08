# CSIG Delay + Available Bandwidth Validation

This directory contains the validation harness for the CSIG delay and
available-bandwidth experiments.

## Modes

The active comparison modes are:

- `baseline_rtt`
- `csig_poseidon_rate`
- `csig_delay_abw`
- `hpcc`

`hpcc` is included only as a reference controller. Its retransmission and NACK
counters should not be compared directly against UEC/NSCC counters.

## Simulator Flags

- `csig_poseidon_rate`: `-nscc_csig_poseidon_rate`
- `csig_delay_abw`: `-nscc_csig_delay_abw`

The delay+ABW harness applies the following explicit defaults:

- `-csig_delay_abw_target_divisor 2.0`
- `-csig_delay_abw_gain 0.125`
- `-csig_delay_abw_low_frac 0.75`

## Build

From the repository root:

```bash
cd htsim/sim
cmake -S . -B build
cmake --build build --target htsim_uec htsim_hpcc --parallel
```

The validation scripts run the simulator binaries through the symlinks in
`htsim/sim/datacenter`.

## Run

From this directory:

```bash
python3 scripts/run_all.py \
  --jobs 8 \
  --modes baseline_rtt,csig_poseidon_rate,csig_delay_abw,hpcc
```

Run the trace-marked scenarios to generate the `CSIG_TRACE` inputs used by the
diagnostic plots:

```bash
python3 scripts/run_all.py \
  --trace \
  --jobs 8 \
  --modes baseline_rtt,csig_poseidon_rate,csig_delay_abw
```

## Parse and Plot

From this directory:

```bash
python3 parsers/parse_all.py
python3 plots/plot_all.py
python3 clean_poseidon_eval/plot_clean.py
```

`plot_clean.py` reads the raw Poseidon-style traces under
`poseidon_style/raw` and writes the clean comparison figures under
`clean_poseidon_eval/figs`.

## Outputs

- `results/raw`: raw simulator output from `run_all.py`
- `results/traces`: parsed `CSIG_TRACE` CSVs
- `results/runs.csv`: per-run scalar metrics
- `results/per_flow.csv`: per-flow metrics
- `results/derived_metrics.csv`: derived control-law metrics
- `plots/figs_clean`: main validation figures
- `clean_poseidon_eval/figs`: clean Poseidon-style comparison figures
