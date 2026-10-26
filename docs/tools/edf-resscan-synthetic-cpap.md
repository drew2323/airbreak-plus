# Synthetic Air11 fixed-pressure CPAP EDF export

`python/edf_resscan.py` can create a research-only ResScan-layout fixture from an Air11/M46 AirBreak SD-card copy:

```sh
python3 python/edf_resscan.py /media/airbreak-copy /media/synthetic-output \
  --synthetic-cpap-pressure 7.5
```

Keep the original card and its recordings untouched. Use a separate output directory (the converter refuses an output inside the input); this operation is not a therapy-device configuration or a clinical record conversion. The generated data are synthetic and must not be represented as actual therapy. The example assigns 7.5 cmH2O to supported pressure channels, including `Press.40ms`, `MaskPress.2s`, `Press.2s`, `EprPress.2s` and available STR pressure summaries, and changes active STR records to fixed CPAP Mode 3. Existing missing samples (`FFFF`) in detailed signals stay missing. An STR row without valid therapy duration/mode remains untouched.

The option currently accepts Air11/M46 input only and forces the M46/V3 CPAP output layout. It rejects another profile override and cannot be combined with `--repair-str`. Air10 is unsupported. The converter reorders/selects signals by channel to the embedded profile layout, fills unavailable profile signals with EDF missing-value samples, rewrites EDF identification and checksums, writes sidecar CRCs, and updates Air11 `Identification.json` identity fields for M46/V3; unrelated files are copied. This does not reconstruct absent measurements, validate clinical accuracy, or establish ResScan compatibility. The author confirmed opening/import in OSCAR; ResScan has not been tested. Do not use this fixture for treatment decisions or compliance claims.

Run focused tests with the Python standard library:

```sh
python3 -m unittest discover -s python/tests -p 'test_edf_resscan_synthetic.py' -v
```
