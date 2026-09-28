# ADI Anvil — Brand and UI Handoff

Version: 1.0 · 27 September 2026 · Review asset, not production UI

## 1. Approved naming

Product name: **ADI Anvil**. Exact tagline: **Frontier Evaluation & Diagnostics Platform**. The new independent application folder is `ADI-Anvil`; the original ADI-Core-Frontier source specifications remain unchanged. Use `adi-anvil` for application/package identifiers. No GitHub remote has been created. Do not substitute ADI Crucible, ADI-Core-Enterprise, Varaha or Vamana in customer-facing Anvil UI.

Name approval does not establish trademark/domain availability; no availability search or registration was performed.

## 2. Brand assets

- [ADI Anvil logo v1](../../assets/brand/adi-anvil-logo-v1.png): generated raster derivative of the user-supplied ADI Labs image, retaining the blue/teal infinity design and replacing the wordmark/tagline.
- [Review mockup](mockups/adi-anvil-v1.html): local, self-contained design demonstration; no backend, paid inference, real identity or external data transfer.

The original logo was not overwritten. Because the new lockup is generated, it is a visually matched derivative, not a claim of pixel-identical vector reproduction. Obtain the original editable vector master for production-perfect mark geometry if needed. This v1 raster has a charcoal background; do not label it transparent or stretch/distort it.

Use the full lockup on sign-in/about/presentation surfaces. In compact navigation use an approved infinity-only asset plus live-text “ADI Anvil”; until that asset is approved, live text is preferable to squeezing the entire raster into a tiny badge. Keep the full tagline available as real text and an accessible image alternative. The mockup shows the generated full logo on its main brand panel and preview dialog.

## 3. Match the existing ADI frontend

Reference inspected: ADI Praxis, specifically its Next.js web app, brand component, console layout and shared theme/token files. Use **Next.js + React + TypeScript + Tailwind** as the Anvil frontend stack. “Same frontend” is implemented as the same technology and visual language, **not the same running application, shared database, imported `@praxis/shared` package or automatic release coupling**.

The reference uses navy top navigation, a blue/teal gradient accent, rounded cards, restrained shadows, pills, clear primary actions, light/dark themes and role-aware navigation. These patterns govern the mockup. Earlier proposed cobalt/sidebar identity in the broad Frontier draft is superseded for the v1.0 design baseline. The full product roadmap still has F01–F10 modules; the mockup presents only the scoped MVP navigation.

| Token | Brand value | Usage |
| --- | --- | --- |
| Navy | `#0A2170` | Header and light-theme primary text |
| Blue | `#2A80D0` | Brand gradients, accents, focus treatment |
| Teal | `#3FAC95` | Brand accent, graph capability highlighting |
| Silver | `#8597A3` | Brand detail, control borders; not small text on white |
| Charcoal | `#212227` | Dark background and logo surface |
| Light surface | `#F5F7FA` / `#FFFFFF` | App background / raised content |
| Muted light text | `#5B6B77` | Readable secondary content |
| Light link | `#1D68B0` | Derived accessible link color |

Brand blue/teal are not automatic success statuses. For small control labels use tested semantic colors; the mockup's primary action is darker blue to avoid white-on-bright-gradient contrast problems. Dark mode uses lighter text and semantic statuses. Accessibility is an acceptance test, not presumed from tokens. Font uses a local/system sans-serif fallback; no third-party font request is required.

## 4. Mockup coverage and interaction

Six local views: Research objectives, Case bank, Evaluate, Diagnostics graph, Reports & releases, Sales Kit. Test theme toggle, case search, case details, graph inspector and preview dialogs. Controls for live execution/customer release/email sending remain disabled, with prerequisites explained. Forms that would create records open a mockup notice rather than falsely showing persisted success. The [Sales Kit](18-AUTOMATED-SALES-KIT-SPEC.md) view previews a digest, not a generated real benchmark result.

The 200-case number is the user's planned collection scope. The three shown cases are invented **synthetic UI fixtures**, not actual Bodhium materials. The screen reports zero actual model runs. Illustrative readiness and fixture observations must not enter sales evidence as measured results. Proposed initial app module routes are listed in the engineering spec.

The graph shows evidence relationships. LangGraph is the execution framework; Neo4j is the graph projection; PostgreSQL is canonical record/checkpoint storage. Advanced TNG/TTM planning and authoring are deferred pending the user's future specification.

## 5. Image-generation provenance

Built-in image generation was used in edit mode, with the supplied `/Users/vasudevansundarababu/Documents/ADI-Logos/ADI-Labs-Icon.png` as reference/edit target. Output was inspected and copied into this project; the original and tool-generated source were left intact. Final prompt:

> Use case: text-localization / logo-brand. Edit target: supplied ADI-Labs logo. Create the ADI Anvil product logo for the same corporate family. Preserve the existing distinctive infinity ribbon emblem exactly in silhouette, proportions, glossy blue/navy/teal gradients, highlight and shading; do NOT introduce a physical anvil symbol or redesign the infinity. Change the large wordmark from ADI-Labs to exactly “ADI Anvil”. Replace the old slogan with exactly “Frontier Evaluation & Diagnostics Platform” in one legible line below, using restrained light silver-blue sans-serif typography, sentence title capitalization as given. Maintain the original charcoal background and premium silver-blue wordmark treatment. Wide landscape lockup, infinity emblem above the wordmark, generous clean margins, tagline wide enough to be clearly legible. No extra text, watermark, decorative elements, or mockup devices. High resolution clean finished logo asset. This is a faithful brand extension, not a new identity.

The requested preservation in the prompt is a design constraint; it does not certify pixel-identical reproduction. Text/visual review of the delivered raster is still required before final brand sign-off.
