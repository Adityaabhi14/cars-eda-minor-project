# Dataset provenance

This directory contains the original, unmodified **Automobile / 1985 Auto
Imports** dataset and its original data dictionary.

- Creator: Jeffrey C. Schlimmer.
- Citation: Schlimmer, J. (1985). *Automobile* [Dataset]. UCI Machine Learning
  Repository. <https://doi.org/10.24432/C5B01C>.
- Dataset page: <https://archive.ics.uci.edu/dataset/10/automobile>.
- Download: <https://archive.ics.uci.edu/static/public/10/automobile.zip>.
- Retrieved: 19 November 2026.
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
- Records: 205. Original columns: 26, including price.
- Format: comma-separated values, no header, `?` denotes a missing value.
- SHA-256 of `imports-85.data`:
  `125db8bd36a84801f7223faf54071d15f85f26c13a9a7aee63375ac46098fb7f`.
- SHA-256 of `imports-85.names`:
  `cc46be835f433f90334c2a7f4183ba4a48eb5077ece85458322a421eeba12ffc`.

The original spellings `alfa-romero` and `peugot` are preserved here. The analysis
uses the display labels `alfa-romeo` and `peugeot` and records these changes.
The output tables are derived adaptations; the original data files are unchanged.

The source combines vehicle specifications from Ward's 1985 Automotive
Yearbook with insurance information. This historical collection is not a
random sample of today's vehicle market. Fuel economy in MPG is not distance
already driven. Currency and dimensional units not explicitly specified in the
data dictionary are labelled **source units** in the analysis.
