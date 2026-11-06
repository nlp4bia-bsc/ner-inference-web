# NLP4BIA design system

The institutional identity is **NLP4BIA · Multilingual NER Platform**, with the
subtitle **Clinical and Biomedical Text Annotation**. The product is a research
workspace developed by NLP4BIA at Barcelona Supercomputing Center, not a separate
commercial service. The interface makes no claims of clinical accuracy,
certification, evaluation scores or institutional adoption.

## Tokens and typography

`app/static/auth.css` owns the shared tokens and components. It is used by public
authentication and private pages; it contains no account or document data.
`style.css` contains only the annotation/catalog/progress/viewer layouts and entity
styles. Pages inherit the same shell instead of duplicating headers/footers.

| Token | Value | Purpose |
|---|---|---|
| --accent | #213970 | BSC blue, primary controls and institutional identity |
| --ink | #192b48 | Main text |
| --muted | #59677d | Supporting text with readable contrast |
| --blue | #315fa8 | Progress and interactive emphasis |
| --paper / --bg | #ffffff / #f5f7fb | Panels and workspace canvas |
| --line | #dce3ed | Subtle component boundaries |
| --success | #246449 | Successful states |
| --warning | #805512 | Expiry approaching or partial results |
| --danger | #a02b37 | Errors and destructive actions |
| --radius | 12px | Main cards; controls use smaller radii |
| --shadow | 0 8px 28px #142c5007 | Restrained depth |

Typography uses the local operating-system sans-serif stack (Inter only if already
installed). There are no Google Fonts, remote font requests or font downloads.
Page titles scale from 30–42px; the public presentation uses 38–58px. Body text is
14–15px, reading text 14–16px, with smaller metadata/captions. Scientific text uses
a local monospace stack and preserves Unicode/whitespace. Large readers limit line
width independently of the surrounding workspace.

Spacing follows an approximately 4px scale, with 16/20/24/32px panel spacing. Logical
CSS properties support future direction-aware layouts; the currently supported
English, Spanish and Catalan interfaces are LTR. RTL translations are not supplied.

## Shared components

`templates/base.html` composes the brand, primary navigation, persistent language
selector, account menu, visible sign-out action, skip link and institutional footer.
`components.html` owns copy, icons and footer macros. Icons are lightweight local
inline SVGs, separate from the unchanged official institutional logo.

Buttons have primary, secondary, text and destructive variants, visible focus and
44px minimum height. Inputs have labels, password reveal controls and meaningful
autocomplete. Native checkboxes/selects/details remain keyboard accessible. Long professional
labels use a full-width field and a wrapping mobile caption; mobile account cards
stack names/emails. Multilingual checkpoints have their own collapsible section,
which preserves existing selections.
Cards, state badges, responsive tables, empty states, notices, loading skeletons,
progress and dialogs use the same color/spacing/border vocabulary. Status words and
numbers accompany colors. No badge alone claims a checkpoint is clinically valid.

Dialogs use native `dialog.showModal`, labeled headings, browser focus containment,
Escape/Close, and focus restoration. Privilege/status/session-revocation actions
show a confirmation with the account and selected changes. Cancellation performs
no write. Small auth feedback is a status notice rather than an intrusive modal.

`auth.js` owns shell controls, in-place locale switching and the shared dialog
helper. `catalog.js` is reused by the read-only Models page and New annotation.
`form.js`, `progress.js` and `viewer.js` keep their respective interactions. No
framework migration or production component library was introduced.

## NER entities and layout

Thirteen explicit canonical entity palettes pair a dark category border with a pale fill.
Offsets, literal labels, mention IDs, model provenance and scores remain visible.
Selected spans use an outline; other spans retain readable text contrast. Nested,
equal-boundary and crossing mentions remain individually selectable. Color is not
the only cue: labels, an outside-text overlap summary, lists and tables expose the
same annotations. Canonical colors are shared across languages/checkpoints; known
aliases reuse that color and new categories use a neutral fallback. Disease is
red/pink, medication blue and procedure green. The full mapping is in spans.js.

The reader offers inline highlights and labeled SVG entity towers. Neither mode
duplicates source text. Inline multiplicity uses a double underline, without word-
breaking counters. Towers allocate independent blocks per source line and center
each tag over its range. Shorter overlapping mentions remain below longer ones;
40px levels keep range marks separate from labels/text. Edge labels retain their
12px font and exact centering using horizontal scrolling when necessary.
Towers show one label per mention, preserve whole display graphemes and expose untouched
half-open source offsets. See [OVERLAP_RENDERING.md](OVERLAP_RENDERING.md).

Desktop uses three panels: documents, original text and entity information. Side
panels/tables scroll within deliberate bounds, avoiding a very tall empty reader.
Tablets use two columns plus a wider entity panel. Phones stack panels, provide a
bounded document tree and an accessible entity-details sheet. The annotation list
is the mobile card representation alongside the scrollable technical table.

The progress panel remains sticky and collapsible. Previously completed jobs open
with compact progress; active jobs show the expanded panel. Percentages still mean
annotated documents divided by actual documents. Countdown uses server timestamps
and monotonic elapsed time. Changing locale never resets the deadline.

## Institutional asset

`app/static/assets/bsc-blue.svg` is the exact uploaded BSC-blue.svg. SHA256:
`7dec16c129362f48657e36109c894ca1ed70062f0a64b48171bd7667361f3b27`.
Its viewBox is `0 0 283.46 69.36`. XML inspection found no script, foreignObject,
external href, event handler or URL reference. The source paths/colors/proportions
were not edited or rasterized. The path-specific .gitattributes entry preserves
the original CRLF and one original trailing space; application code retains normal
whitespace checks. Footer images have descriptive alternative text,
explicit dimensions, automatic proportional height and local loading. The logo is
approximately 230px wide, also on phones. Use the source asset rather than a redraw;
additional institutional branding review remains the deployer's responsibility.

## Translations and maintenance

`app/ui_i18n.py` and the existing auth vocabulary are the shared source for EN/ES/CA.
Regenerate the browser dictionary after editing strings:

```sh
python -m scripts.build_ui_translations
```

`data-i18n` identifies presentation copy explicitly; document text is never scanned
or translated. Locale changes retain input files/text, document language, model
IDs, filters and results. `Intl` formats user-facing numbers and local date/time.
Scientific IDs/labels, version strings and original model provenance remain literal.
Catalog availability explanations and UI descriptions have translated vocabulary;
new administrator-authored metadata needs corresponding translations if localized.

Jinja templates are excluded from vanilla HTML Prettier: its attribute formatting
previously corrupted conditional attributes. All templates compile in regression
tests; Ruff and Prettier still check Python and static JS/CSS. Generated i18n.js is
checked against its source rather than reformatted independently.

## Verification scope

See [REDESIGN_VERIFICATION.md](REDESIGN_VERIFICATION.md) and the screenshot gallery
for actual browser resolutions, interactions, automatic accessibility checks and
security regression. The design targets WCAG 2.2 AA; automated checks and keyboard
probes do not establish conformance certification or replace assistive-technology
and institutional usability review.

The [15-pair palette check](security/v5-contrast-palette.json) records normal-text
foreground/background ratios of at least4.5:1. It is bounded to design tokens, not
a substitute for the incomplete browser/overlap assessments or human review.
The [V5.1 entity palette check](security/v5.1-entity-palette.json) additionally
records text and border contrast above 4.5:1 for all 13 canonical categories and
the neutral fallback.
