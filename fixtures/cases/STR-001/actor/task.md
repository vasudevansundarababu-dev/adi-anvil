# Market-entry decision

A fictional company can launch in exactly one region this quarter. Maximum launch investment is USD 120,000. Launch readiness must already be approved; pending review is not approval. Service demand cannot exceed capacity.

For each region compute served accounts = min(demand, capacity), then quarterly contribution after fixed operating cost = served accounts × contribution per account − quarterly fixed operating cost. Choose the feasible region with the greatest quarterly contribution after fixed operating cost. Launch investment is a separate budget constraint, not a quarterly operating cost in this exercise. No additional funding, outsourced capacity or assumed future approval.

Return JSON with calculations, `selected_option`, `constraint_checks`, `evidence` and `limitations`. Cite exhibits.json. State that demand/contribution forecasts are assumptions and readiness is a supplied business condition, not your legal determination. This is an original synthetic test, not a real investment recommendation.
