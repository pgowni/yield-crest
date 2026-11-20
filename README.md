# YieldCrest

YieldCrest helps outdoor advertising operators decide which campaigns to accept, which boards to allocate, and when to preserve availability for potentially better business.

It combines inventory, campaign enquiries, booking history, payment records, seasonal demand, and maintenance requirements. Selecting a campaign brings together requests competing for overlapping dates and approved boards, each with its own confirmation probability and reservation deadline.

Machine-learning models estimate future enquiry volumes, offer-confirmation probabilities, and achievable rental rates. A simulation and allocation engine compares feasible plans, accounting for revenue shares, operating costs, maintenance downtime, and opportunities displaced by accepting a campaign.

For example, Lotus Retail requests Ameerpet for ₹43,000. Meridian Ads offers ₹65,000 for overlapping dates but also accepts Banjara Hills. Ameerpet needs maintenance. The system evaluates confirmation chances, alternative boards, seasonal demand, and maintenance windows. It might recommend Lotus on Ameerpet, Meridian on Banjara Hills, and maintenance after Lotus’s campaign.

Users see recommended assignments, expected net contribution, uncertainty ranges, and the confirmation probability at which the preferred decision changes. Adjusting prices, dates, or probabilities recalculates the comparison.

## Repository layout

| Folder | Contents |
|---|---|
| [yieldcrest](yieldcrest) | Calendar/finance domain logic, forecasting, booking decisions |
| [yieldcrest/ui](yieldcrest/ui) | Dashboard pages, shared components, floating chat and styles |
| [data](data) | Persistent SQLite database and generator assumptions |
| [data/splits](data/splits) | Exact training, validation, test, final-fit and replay CSV snapshots |
| [artifacts](artifacts) | Fitted model artifact loaded by the app |
| [reports](reports) | Model comparison metrics and chronological replay results |
| [scripts](scripts) | Explicit offline generation, export and training commands |
| [tests](tests) | Financial, calendar, leakage and tool-protocol regression checks |
| [docs](docs) | Implementation checklist |
| [archive/legacy](archive/legacy) | Earlier two-board demo files preserved for reference |

The root [streamlit_app.py](streamlit_app.py) remains the deployment entrypoint.
[requirements.txt](requirements.txt) and .streamlit/config.toml remain in the root
so the existing Streamlit deployment continues to find them.

## Run the app

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app opens [data/yieldcrest.sqlite](data/yieldcrest.sqlite) read-only and loads
[artifacts/forecast.joblib](artifacts/forecast.joblib). User interactions neither
regenerate data nor retrain models. Each browser session owns its what-if controls.

## Reproduce the models

```bash
python -m scripts.export_datasets
python -m scripts.train_models
python -m tests.validate
```

The exporter writes checksummed feature snapshots. Training reads those same CSVs,
uses chronological validation to select the offer-close classifier, evaluates later
quotes, and then refits on the final-fit snapshots. Exported rows reproduce the
previous evaluation metrics. See [the dataset guide](data/splits/README.md).

The achieved-rate adjustment was fitted on accepted deals without a held-out test.
Its training file is supplied and that evaluation gap is explicit. The offer
classifier underperformed the historical win-rate baseline on its final test period.

The one-time generator is `python -m scripts.generate_data`. It refuses to overwrite
an existing database. Regeneration is an intentional offline action.
Only load the trusted fitted artifact committed to this repository.

The application runs without LLM API keys. The floating assistant and AI explanation controls have been removed.

## Reviewer workflow

- **Overview** shows current inventory, prorated November booked gross rent,
  additional forecast net contribution, and overdue invoices.
- **Enquiries** checks confirmed location alternatives and opens the selected request.
- **Decisions** compares accepting a firm offer with preserving its dates, then evaluates
  up to three independent uncertain offers across feasible whole-campaign allocations.
- **Operations** compares service windows and jointly chooses maintenance dates and bookings.
- **Evidence** shows model splits, baseline comparisons, replay and generator assumptions.
- **Ask YieldCrest** floats across the workspaces and preserves conversation through navigation.

## Interpretation

The generator's festive period is December 5–20, an illustrative retail period.
The 80% Meridian Ads share and ₹5,000 priority tolerance are editable demo assumptions.
Faces 1–5 are reserved in the generator for review scenarios; operator-declined
offers are excluded from offer-close training.

Every alternative sees identical future paths. Future requests target a single face,
and future bookings follow an online first-feasible, positive-contribution policy.
Current-plan search is exhaustive for three requests. A skipped request is explicitly
declined; a failed hold releases its face to subsequent demand after expiry.
Close outcomes are assumed independent. A longer hold keeps the displayed close
chance fixed until an operator changes it.

Accepted prices reflect historical selection and negotiation. Local rate-duration
samples are pooled with portfolio observations. P10–P90 describes simulated outcomes,
not parameter uncertainty. Cash scenarios use settled invoice lags and assume no default.

Synthetic replay demonstrates implementation and chronology. Real data is required
to validate forecast accuracy and revenue uplift.
