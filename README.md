# YieldCrest

Synthetic AdPlay booking decision demonstration. Fixed snapshot 19 November 2026.
Run `pip install -r requirements.txt`, then `streamlit run streamlit_app.py`.

The committed `yieldcrest.sqlite` contains the full dataset. The running app opens
it read-only. It never seeds data or trains models on a user interaction.
Each browser session owns its scenario controls and conversation.

## Review

- **Decisions / Accept or preserve dates** compares identical future demand across two calendars.
  The current offer is firm. Gross break-even includes share, costs and the selected lighting policy.
- **Allocate competing requests** evaluates every feasible current assignment and all close/fail
  combinations for up to three independent uncertain requests. A skipped request is explicitly declined.
  Holds that fail release their actual dates to subsequent enquiries. Requests must meet their full duration.
- **Operations** compares service windows by expected rental contribution displaced and blocks selected
  windows during joint allocation.
- **Evidence** shows chronological splits, baselines, limits and generator parameters.
- The LLM can inspect figures and call bounded calculation functions. It cannot write to the database.

## Gemini connection

In Streamlit's app settings add a server secret:

```toml
GEMINI_API_KEY = "your key"
# Optional. Without this setting the app discovers a text model available to the key.
# GEMINI_MODEL = "your supported model ID"
```

Keep keys out of GitHub. A personal session-only key can also be entered in Assistant connection.
No vendor API is called until a question is submitted. Synthetic scenario details and the recent
conversation are sent to Gemini at that point. Financial arithmetic stays in Python.

## Offline data and model work

`generate_data.py` is an explicit one-time generator and refuses to overwrite an existing database.
Generator assumptions are in `data/generator_parameters.json`. The illustrative festive period is
December 5–20, not an official holiday calendar. An 80% Prakash share and ₹5,000 tolerance are demo inputs.

`train_models.py` fits and stores the enquiry-count, offer-close and achieved-rate models in
`models/forecast.joblib`. `validate.py` runs chronology, calendar, cost and leakage regression checks.
Regeneration is intentionally manual. Models load only trusted artifacts from this repository.

## Interpretation

The offer classifier is experimental and did not beat the win-rate baseline on the final synthetic
test period. The count model includes zero-arrival face-days. Joint lead-duration/rate templates
come from accepted deals and therefore reflect historical operator selection. Local price samples
are blended with portfolio samples. P10–P90 shows simulated outcome spread, not parameter uncertainty.
Raw local and pooled sample counts and completed seasonal periods are displayed.

Future enquiries target one face. Future booking decisions follow an online, positive-contribution,
first-feasible rule. The simulation never chooses future bookings with knowledge of later arrivals.
The current-plan search is exhaustive for three requests; it is not a guarantee of globally optimal
revenue under every possible future selling policy.

Historical real-data testing is needed before relying on prices or claiming revenue uplift.
Pending invoices are displayed separately from settled payment-time samples. Receipt forecasts are
conditional on those timing samples and on the no-default assumption, not a guarantee of collection.

## Earlier fixtures

The previous yieldcrest_step2.sqlite, yieldcrest_model.py, seed_database.py,
seed_history.sql, train_close_model.py, portfolio.py and operations.py remain as
legacy demo files. The active app uses domain.py, forecasting.py, decision_engine.py,
yieldcrest.sqlite and the ui modules. The current dataset/model source is generate_data.py
and train_models.py. Legacy scripts are independent of the current application.
