# Report Plotting

This directory generates only the report artifacts used for the CSIG delay and
available-bandwidth evaluation.

## Inputs

The generator reuses the parsed outputs and raw traces produced by
`validation/csig_delay_abw`:

- `csig_delay_abw/results/runs.csv`
- `csig_delay_abw/results/per_flow.csv`
- `csig_delay_abw/poseidon_style/raw`

The plotting logic is imported from the existing `csig_delay_abw` scripts, so
the figures stay consistent with the validation harness without maintaining a
second copy of the plotting implementation.

## Generate

From this directory:

```bash
python3 generate_report_figs.py
```

The output directory is `figs` by default. To write somewhere else:

```bash
python3 generate_report_figs.py --out-dir report_figs
```

## Outputs

The generator writes exactly these files:

- `figs/2_incast_request_completion.png`
- `figs/7_multihop_fairness.png`
- `figs/fig21a_ablation.png`
- `figs/fig17_concurrency.png`
- `figs/metrics_summary.csv`
