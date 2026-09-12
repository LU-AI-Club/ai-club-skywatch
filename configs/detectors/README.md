# Detector configs

One YAML file per detector holds its tunable thresholds, so numbers live in
config (and in version control) rather than being hard-coded. Each team adds its
own file when it reaches the baseline/config lane, mirroring the maritime
pattern (`configs/detectors/m003_proximity.yaml` in the platform repo).

A detector loads its config into a frozen dataclass (see the maritime
`M003Config` / `load_m003_config` pattern). The worked example
(`air/detectors/_example_altitude`) uses dataclass defaults directly and needs
no file; real detectors should externalize thresholds here so evaluation can
sweep them.
