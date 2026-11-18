# UI defects reported 18 November 2026

User screenshots and explicit requests authorize these bounded UI corrections.

## UI-20261118-01: Open Weight catalog and creation layout

Reported: long checkbox prose and one-model creation dropdown make shared-token
setup difficult. Required: identical selectable tables in Models & Keys and new
Hugging Face profile creation; Select, Name, Version, Repository and Terms columns;
select all / clear; one saved exact credential version attached to all selections.

Implementation uses the existing atomic catalog registration endpoint in both
paths. Each exact model retains its immutable identity; the shared credential is
selected once. No new database schema, model dispatch or terms acceptance.
Terms links open the repository's version-pinned model card for its terms and
license information; following a link does not accept the terms.

## UI-20261118-02: Projects and Execution search alignment

Reported: narrow inputs, distant Search buttons and inconsistent vertical alignment.
Required: flexible full-width input, adjacent Search and aligned Import/New Execution
actions, with wrapping at small widths. Scoped shared toolbar styles apply to these
two screens without changing other toolbar layouts or search behavior.

Local verification: TypeScript check and production webpack build PASS. Chrome
synthetic API journey PASS (1 test,3.1 seconds): both bulk paths send all32 exact
versions with the same credential; existing immutable edit and Run selection
remain intact; Projects/Execution desktop input/button edges align within2px,
button gap under20px;390px mobile has no document overflow. Actual screenshots
visually inspected. Initial synthetic Execution response omitted runs/groups,
corrected in test harness; initial incomplete attempt retained, not counted PASS.
No external provider or Authoring calls. Not deployed yet.
