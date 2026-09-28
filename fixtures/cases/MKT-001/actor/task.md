# Promotion decision

You advise a fictional retailer. Choose one of the supplied promotion options to maximize units sold while satisfying a gross-margin floor of 30% and stock of 140 units. Use only exhibits.json. No replenishment, other promotions or external demand assumptions are allowed.

For every option calculate discounted unit price, capped units sold, revenue, gross profit and gross margin (profit/revenue). Give the chosen option, identify constraint violations in alternatives, cite the exhibit and state that demand is an assumed point estimate, not proven causal uplift. Round currency to cents and percentage display to two decimals; retain precision for decisions. Explain the final recommendation briefly; no private chain of thought is requested.

Return a JSON object with `options` (array of calculations), `selected_option`, `constraint_checks`, `evidence` and `limitations`. Every calculation must identify its option. The objective is unit sales, not maximum gross profit. This is a synthetic test case.
