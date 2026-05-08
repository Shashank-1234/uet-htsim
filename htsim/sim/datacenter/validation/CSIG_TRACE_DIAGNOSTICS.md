# CSIG Trace Diagnostics

Build the UEC and HPCC simulator targets:

```bash
cd /Users/shashankdutt/Downloads/HTSIM/uet-htsim
cmake --build htsim/sim/build --target htsim_uec htsim_hpcc -j 8
```

Run the focused CSIG trace scenarios:

```bash
cd /Users/shashankdutt/Downloads/HTSIM/uet-htsim/htsim/sim/datacenter/validation/csig_delay_abw
python3 scripts/run_all.py \
  --jobs 8 \
  --trace \
  --modes baseline_rtt,csig_poseidon_rate,csig_delay_abw,hpcc
```

Run one trace cell directly:

```bash
cd /Users/shashankdutt/Downloads/HTSIM/uet-htsim/htsim/sim/datacenter/validation/csig_delay_abw
scripts/run_one.sh \
  cm/C_queue_pressure_32_1MB.cm \
  csig_delay_abw \
  results/raw/C_queue_pressure_32__csig_delay_abw.trace.out \
  -end 100000 \
  -debug_flowid 1 \
  -csig_trace
```

Inspect emitted diagnostics:

```bash
rg '^(CSIG_TRACE|CSIG_FLOW|CSIG_SWITCH)' results/raw/*.trace.out
```

Parse the trace outputs and regenerate diagnostic plots:

```bash
python3 parsers/parse_all.py
../../../../../.venv/bin/python plots/plot_all.py
../../../../../.venv/bin/python clean_poseidon_eval/plot_clean.py
../../../../../.venv/bin/python poseidon_style/plot_poseidon_style.py
```

Normal runs do not emit `CSIG_TRACE`, `CSIG_FLOW`, or `CSIG_SWITCH`; pass
`-csig_trace` with `-debug_flowid <id>` when trace diagnostics are needed.
