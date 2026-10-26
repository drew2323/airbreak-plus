# edf_resscan

## Name

`edf_resscan.py` — convert an AirBreak EDF-superset SD-card copy into the EDF channel layouts expected by the selected original ResMed profile.

## Synopsis

```text
python3 python/edf_resscan.py INPUT_DIRECTORY OUTPUT_DIRECTORY [OPTIONS]
```

## Description

The converter reads an existing SD-card copy, selects a layout from the device identity or an explicit profile, and writes converted files to a separate output directory. It does not modify the input card. It converts EDF headers and channel order, preserves available samples, supplies EDF missing-value samples for layout channels absent in the source, recalculates per-file CRC sidecars, and updates the identity CRC when identity metadata is rewritten. Files not handled as EDF or identity metadata are copied unchanged. Channels not present in the selected original profile are omitted.

Use this for actual recordings only when the source data and selected device profile are correct. Preserve the original card copy as a backup and inspect the generated directory before importing it. The tool is not a device configuration utility and does not establish clinical validity or guarantee compatibility with every ResScan release.

## Options

| Option | Meaning | Default |
|--------|---------|---------|
| `--profile MID:VID` | Select output schema using decimal platform and variant identifiers, e.g. `46:3`; bypasses source identity parsing for profile selection | Read source identity |
| `--overwrite` | Allow updating a non-empty output directory | Off |
| `--from-date YYYY-MM-DD` | Convert sessions on or after the date; STR and identity metadata are still updated | All sessions |
| `--repair-str` | Estimate empty STR days from source PLD/SAD/EVE recordings | Off |
| `-h`, `--help` | Show command help | — |

The output directory must not be the input directory or inside it. Use a new, empty output location unless intentionally updating an existing conversion with `--overwrite`.

## Real-recording conversion

1. Copy the complete SD card to a working directory without changing its contents.
2. Keep a separate backup of that copy.
3. Run the converter to a different directory. Normally, the source `Identification.tgt` or `Identification.json` selects the profile:

```sh
python3 python/edf_resscan.py /path/to/card-copy /path/to/converted-card
```

For a source whose identity is missing or cannot be read, select a known profile explicitly. For example, Air11 M46/V3:

```sh
python3 python/edf_resscan.py /path/to/card-copy /path/to/converted-card --profile 46:3
```

An explicit profile controls output schema selection. If an identity file is present, the converter updates it to match the selected profile; malformed JSON remains an error because it cannot safely be rewritten. If both JSON and TGT identity files exist, only the selected identity representation is copied to output, avoiding contradictory identities.

To estimate missing daily STR records from source recordings, use `--repair-str`. Estimated values are not original device measurements; review them carefully before use. This option cannot be combined with synthetic pressure export.

## Research-only synthetic Air11 CPAP fixture (optional)

This mode is not an ordinary recording conversion. It generates a research fixture and must not be presented as an actual therapy record or used for treatment, compliance, or clinical decisions. Preserve the original recordings and use a separate output location.

```sh
python3 python/edf_resscan.py /path/to/air11-copy /path/to/synthetic-output \
  --synthetic-cpap-pressure 7.5
```

It currently accepts Air11/M46 source identity and emits M46/V3 CPAP layout. It rewrites Air11 `Identification.json` or `Identification.tgt` metadata and recalculates CRCs. A fixed pressure is applied only to supported pressure signal samples and active STR pressure fields; missing samples remain missing, and therapy settings remain otherwise unchanged.

An optional display-only flow-driven pressure variant is available:

```sh
python3 python/edf_resscan.py /path/to/air11-copy /path/to/synthetic-output \
  --synthetic-cpap-pressure 7.5 --flow-driven-pressure
```

This heuristic uses matched `Flow.40ms` to vary displayed pressure while preserving flow samples and fixed therapy settings. It uses frozen thresholds (absolute flow onset 1.4 L/s, saturation 2.0 L/s, 120 ms event-gap allowance) and caps peaks at 9.5 cmH2O for a 7.5 baseline. The values were calibrated on one development snapshot and are not estimated per migration. The 2-second pressure channel averages mapped pressure, attenuating brief peaks. This is not physiological reconstruction and does not claim clinical validity. `--synthetic-cpap-pressure` only supports M46 input; it conflicts with other output profile overrides and with `--repair-str`.

## Output and verification

The selected EDF channel order is defined by embedded profile layouts. Air11 M46/V3 channel lists are explicit ordered layouts matching the supplied ResScan VID 03 schemas; `Crc16` is appended by this converter as the trailing EDF integrity signal. EDF CRC sidecars are recalculated for output bytes. Check command output and the output directory for expected channel files before importing.

## See also

- [Air11 EDF signal reference](../as11/edf_signals.md)
- [Air11 EDF header reference](../as11/edf_header.md)
