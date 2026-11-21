# Consumed e49 QA operators

These text files preserve the exact public Python bytes executed during the
fresh e49 QA qualification campaign on 20 November 2026 (Chicago). They are
historical evidence, not reusable deployment commands. Their names, operation
intents, candidate directories and expected baselines are consumed. Do not replay
them. Prepare a fresh reviewed operation against actual current state.

| Archived source | Executed SHA-256 |
| --- | --- |
| stage-bootstrap.py.txt | 6d61a589ba321fbbcbcaf7bd69871417a9d315ccef83121f8f5c72456ca168a9 |
| stage-controls.py.txt | ed99b2f7bbfacb934092a733aaecf7c182c472b4ad93754a3e2171f847fced86 |
| native-control.py.txt | 71681f97c371a8818bc48992f20c4119fc6969548923140966a7865c8cf81dda |
| capture-probe.py.txt | 6b6178ec1d5e5cc2911919794d433254554e46fcd51e79a4504c6f2b50603379 |
| observer-helper.py.txt | df957d4ae64990047f7a82581c3d3324cba6b3c3e5c8402947d5915c20197929 |
| observer-selftest.py.txt | bb07d34a63f2538c985c213e7ea3d6d39cd75777db276e63ac858018573bd526 |
| supplement.py.txt | 4b78f3a91e2c82458610a9f2345a1850c20ebd2bcea0387138ba4db33d8dddfa |
| transport-exclusive.py.txt | 5d1ef101608d361fc0397b2abe1c3b33214a0e8ae15e9ed76c3c1d99c20fa040 |
| validate-capture-candidate.py.txt | 8a53a4838b48e8e8ef30b72f6afeb5b59bd7a0e563c4596948b81a259f072412 |
| capture-candidate-readback.py.txt | 120e39c6c60df2e266c37e13a8b030079e8f5a149872843190bc8541f6b3c673 |
| stage-component-review.py.txt | 52a30e73c5f53ef05502a70972c59074fb8412a83af998dde0f8f640cbbdf23b |
| qualification-readback.py.txt | 312c97c9aa47085ae6d94e4d8a4711e1503882ee88ae2679edce580de297c3f5 |
| accept-components.py.txt | 53fef94c01182f72b7b2864964fa7e11b92062552889e2585672b84c152087a1 |
| validate-both-candidates.py.txt | b309dd6ae6e9abc98772daa30893bf87105d6b3333f1fb0b626525b85060c3df |
| rollout.py.txt | 6f4c13baa8aa96f0f72e1bb875ab7c354311a680d20c94cf972254794a543cec |
| serving-readback.py.txt | 716be4bc16ec71c065992c10bbbdd819e51a0fad25c103a3d2194eabb249b4ea |
| installed-readback.py.txt | 5f8d5b6a1cf5ed73ec0c8160dc9901ec5edc704e23e87386aa56193df544e101 |
| serving-scratch-control.py.txt | 95e01ba5c5ddd5a782d4d95de65da867340d5eb47d77fd3241994066bd20176e |
| http-smoke.py.txt | 38e465aad7134b7affd8e87be637320b9c0bd190e295f4b8689ebc8bf9940f01 |

No credentials, private configuration, task payloads or raw execution logs are
archived here. Synthetic fixture credentials are generated only at runtime into
private files. These operations grant no legal, data-rights, task-admission,
spending or model-performance approval. See `BUILD-STATUS.md` for actual current
deployment and qualification state; passing observations alone are not serving
acceptance.
