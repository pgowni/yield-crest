# Model datasets

All rows are synthetic and derived from the committed database at the fixed
19 November 2026 snapshot. The manifest records feature columns, targets, row
counts, file checksums and the source database checksum.

| File | Rows | Role |
|---|---:|---|
| [offer_close/train.csv](offer_close/train.csv) | 329 | Quotes and known outcomes before 1 March 2026 |
| [offer_close/test.csv](offer_close/test.csv) | 53 | Quotes from 1 March through 31 July 2026 |
| [offer_close/validation/train.csv](offer_close/validation/train.csv) | 229 | Earlier training period for algorithm selection |
| [offer_close/validation/validation.csv](offer_close/validation/validation.csv) | 42 | Quotes from 1 July through 31 October 2025 |
| [offer_close/final_fit.csv](offer_close/final_fit.csv) | 426 | Final deployed classifier fit after evaluation |
| [demand/train.csv](demand/train.csv) | 9,480 | Daily counts before 1 March 2026 |
| [demand/test.csv](demand/test.csv) | 3,156 | Daily counts from 1 March through 18 November 2026 |
| [demand/final_fit.csv](demand/final_fit.csv) | 12,636 | Final deployed demand-model fit after evaluation |
| [achieved_rate/train.csv](achieved_rate/train.csv) | 267 | Accepted prices used to fit the achieved-rate adjustment |

The achieved-rate model had no held-out test in the original implementation.
This export preserves that fact. Its target is log(gross media rent / campaign days).

The [demand/replay](demand/replay) folders contain the daily training rows and next
30 days for each rolling decision date. Validation selects the first 7, 14 or
30 test days for each replay horizon.

Only columns listed under features in [manifest.json](manifest.json) enter a model.
Offer IDs, client IDs and dates are included to audit chronology. The target
won is 1 for a booking and 0 for a lost offer.

The validation and later test training windows overlap because training expands
through time. Final-fit data includes evaluated observations after evaluation.
The final-fit snapshots must never be used to report held-out accuracy.

Training reads these CSVs directly and verifies their checksums.
To intentionally refresh the snapshots from the database, run
`python -m scripts.export_datasets` at the repository root, then
`python -m scripts.train_models`.
