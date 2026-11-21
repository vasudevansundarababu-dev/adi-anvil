# Owner request: remove pending-TIN verification from the benchmark scope

Please create approved successor revisions of these two KYC v8 tasks:

- Teen Joint: `2291de2d-5d6c-41fe-9d8d-e95278f3f3e8`, current approved record
  `070604bd-64c6-4d23-afbe-5f2077b68371`.
- Custodial: `e63aee92-4f4f-4624-9ef2-d4fd0e9d6c5a`, current approved record
  `ecc4f6f5-0af9-4da7-ba0b-0e40016ba7b5`.

I authorize removing pending-TIN verification from this pilot's task scope. Remove
the pending-TIN verification step (currently S5 step 3, zero-based index 2), not
just its tool value. Remove or revise dependent task instructions, required
outputs, task-specific rubric criteria, reference answers and failure handling
that require this verification. Keep unrelated identity, address, authority,
screening and account checks unchanged. Do not substitute document.check or
another tool and claim that it verifies a TIN.

This is a benchmark scope limitation, not a finding that TIN obligations do not
apply. Preserve policy-source bytes and hashes. If the published template requires
this step or criterion, report that constraint before exporting; do not silently
change the template, policy or applicability decisions. Otherwise retain the
exact published v8 template and its hash.

Keep original approved records immutable. Record predecessor/successor IDs,
the exact changed JSON pointers, rationale, owner identity, approval timestamp
and approval receipt. Obtain the Product Owner's actual console approval; this
request is not itself a system-generated approval receipt.

Export one complete replacement ZIP containing all four products. Keep Adult
Joint and Individual approved records unchanged. Regenerate actor projections,
private references and all canonical asset/package hashes from the successors.
Include a machine-readable change record with the explicit limitation:
"Pending-TIN application verification is excluded from this benchmark. Results
do not establish TIN verification or complete regulatory compliance."

No dataset, hidden cases, expected case decisions or Gym evaluator configuration
is required from Authoring. Gym owns that setup. No live calls or integration
dispatch is requested.

## Gym finalization boundary

The private 200-case context and 20 policy-cell bundle is staged and verified on
QA; the seven-rule/50-evaluator plan is prepared. Do not edit that frozen bundle
in place. After the new ZIP is validated and imported, bind exact successor task
revisions to a new dataset/context registration and genuine owner-reviewed
policy subjects. Review all scoring requirements against the scope exclusion;
retain unrelated criteria and do not count excluded TIN verification as passed.
Record the limitation in run/report scope. Exact evaluator configuration IDs,
runtime binding proof, case/rights review and policy intervals remain required;
staging files is not completion of these bindings.
