# Local data

`words.txt` is ENABLE, downloaded from [dolph/dictionary](https://github.com/dolph/dictionary/blob/master/enable1.txt). `common.txt` is that repository's [popular word subset](https://github.com/dolph/dictionary/blob/master/popular.txt). Source URLs, file hashes and counts are recorded in the two source JSON files. These files are bundled locally; ordinary analysis makes no network requests.

Dictionary membership and commonness do not establish game acceptance. `accepted.txt` and `rejected.txt` are empty evidence ledgers initially; use only observed verdicts. `scoring_profile.json` is explicitly uncalibrated.

`templates/` contains generated glyph masks and provenance. No font binaries are copied. Recognition confidence is a shape/quality measure, not a calibrated probability of accuracy.
