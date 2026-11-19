# YieldCrest implementation checklist

- [x] Calendar comparison of a firm offer against preserving festive dates.
- [x] Learned daily enquiry counts including zero-enquiry face-days.
- [x] Learned offer-close probabilities with dated prior-client features.
- [x] Logistic and shallow random-forest comparison with chronological validation/test.
- [x] Paired rate-duration samples, pooled local/portfolio evidence, learned achieved-rate adjustment.
- [x] Whole campaign feasibility, confirmed alternatives, existing bookings, packages.
- [x] Exhaustive current allocation across independent uncertain offer outcomes.
- [x] Failed holds release exact dates to remaining future demand after expiry.
- [x] Gross-to-net costs, operator lighting choice, partner share and priority tolerance.
- [x] Invoice-linked cash timing and overdue balances displayed separately.
- [x] Feasible maintenance windows ranked using forecast opportunity cost.
- [x] Selected service window constrains current booking allocation.
- [x] Reviewer probability sweep, break-even, P10/P90 and zero-revenue chance.
- [x] Gemini tool calling, bounded recalculations, multi-turn interface and calculation trace.
- [x] Chronology/leakage, calendar, financial and tool-protocol regression checks.
- [x] Synthetic T−30/T−14/T−7 rolling enquiry-count replay.
- [x] Verify deployed controls against the committed model outputs.
- [ ] Live Gemini response and recalculation with an owner-provided key.

## Operating assumptions visible to the reviewer

- All evidence is synthetic. Two completed illustrative seasonal periods exist.
- Festive period is December 5–20, an invented retail period rather than official dates.
- Generator reserves faces 1–5 from November 19 for review. Operator-declined records
  are excluded from offer-close training.
- Current offer comparison assumes a firm offer; portfolio controls handle uncertainty.
- Current plans are chosen before close outcomes are revealed. Skipped requests are
  explicitly declined; they are never silently reclaimed after offer expiry.
- Every plan sees identical future scenarios. Future buyers accept one face and whole
  campaign dates. The future selling policy accepts the first positive feasible demand.
- Close outcomes are assumed independent. Changing hold expiry holds close probability
  constant unless the operator changes it.
- Revenue sharing and the priority tolerance are editable demo settings.
- Historical accepted rates reflect selection and negotiation. Simulated outcome bands
  exclude parameter uncertainty.
- The classifier's final synthetic holdout underperformed the simple baseline.
  The Evidence page reports the result.
- Conditional cash receipts assume the observed invoice timing and no defaults.

## Real-data pilot

Inspect record completeness and invoice linkage. Refit with time splits and compare
against baselines. Count distinct genuinely available episodes and seasonal periods.
Counterfactual revenue from declined offers remains unobserved.

## Verified hosted examples

A ₹12,000 gross Prakash offer on Ameerpet has a negative advantage on the original
dates and a positive advantage when moved five days earlier. The joint service
planner chooses December 10–11 to preserve current campaigns. Enquiry navigation,
cash timing and the Evidence view were checked on the deployed app.


## Reproducible model inputs

The exact feature rows are committed under data/splits. Offline training reads those
CSVs directly. Runtime code lives in yieldcrest; scripts, tests, artifacts and reports
have dedicated folders. Earlier fixtures are preserved under archive/legacy.
