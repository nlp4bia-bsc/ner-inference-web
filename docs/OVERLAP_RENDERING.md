# Original-coordinate overlap rendering

Annotations carry id, document_id, label, start, end, text, optional score and
model_id. Their half-open spans use Unicode code points. The inference merge and
BRAT export both reuse domain.validate_surface; canonical_annotations validates
viewer records against the same unchanged original text. No visualization filter
is applied to exports or saved annotation records.

spans.js implements a sweep over start/end events clipped to the requested text
fragment. At each boundary, ending annotations leave before starting annotations
enter the active set. Each atomic segment therefore has a constant set of IDs.
Adjacent spans share no artificial overlap; equal, nested and crossing spans all
remain distinct. Empty segments are not drawn; unannotated text is a normal text
node. Joining segment text exactly reconstructs the original fragment.

JavaScript first uses Array.from(text) to index Unicode code points. It never
uses Python offsets directly as UTF-16 substring indices. Search similarly maps
code-point positions back to DOM text-node UTF-16 offsets for the browser Range.
Combining characters, emoji, non-Latin text, CRLF and tabs are not normalized.
CSS pre-wrap preserves whitespace; the scientific source remains unchanged.

Example: A=[0,5), B=[4,9) yields [0,4):A, [4,5):A+B, [5,9):B.
Two additional annotations on [4,9) remain individually selectable. A double
underline marks multiplicity; a summary outside the source counts overlapping
annotations. No generated counter is inserted into a word.

A greedy interval allocator assigns stable display lanes to intersecting spans.
Lane numbers appear in the alternative mention list. The inline text uses a soft
highlight and underline. Native tooltips include all covering categories, complete
surfaces and exact half-open ranges. Display segments keep whole graphemes when a
model boundary splits a combining sequence; this does not change stored offsets,
surfaces, selection details or exports. The original sweep remains authoritative
for actual overlap counts, so visual grapheme expansion invents no scientific overlap.
Selecting a region opens a button for every covering annotation; selecting one
highlights all its fragments and shows its own label, complete surface, offsets,
model and actual confidence. This works with pointer, touch, Enter or Space.
The mention list provides direct selection without relying on color or hover.

The alternate **Entity towers** mode uses a local SVG renderer in `towers.js`.
Source lines wrap at grapheme boundaries, preferring whitespace, and concatenate
to the exact fragment, including CRLF. Each annotation has one labeled, keyboard
selectable chip, even across words/lines. Continuation brackets retain its ID and
exact original offsets. Full surfaces/ranges/provenance are available in accessible
names, tooltips and the inspector. Each source line owns an independent tower
block. Spans are placed in ascending original range length: shorter intersecting
mentions remain nearest the source and larger mentions stack above them. The
allocator reserves both the range and its centered label, using 40px lanes.
Labels are centered on `(visibleStartX + visibleEndX) / 2`, including spans near
line edges. Short range caps stay within their own lane; no vertical connector
passes through another label or through the text. Line blocks have separate
vertical space, so towers never enter the preceding source line.
Captions remain at 12px without SVG scaling or text compression. When a centered
edge label extends beyond the source column, measured gutters expand the SVG
and the reader scrolls horizontally instead of shifting or shrinking that label.
SVG prefix geometry converts code points explicitly; split graphemes get whole
visual glyphs while retaining their original ranges. Selection survives redraws;
resize, filters, chunk changes and locale switches redraw the same records.

Range marks are invisible by default (`opacity:0`, preserving their geometry).
Only activating a tower label with click, Enter or Space reveals that annotation's
marks, including wrapped continuations. Activating it again hides them; selecting
another label hides the previous marks. `aria-pressed` exposes this toggle state.
Inspector selection alone does not reveal marks. Changing document/reader mode or
filtering out the active mention clears the reveal; resize/locale redraws retain it.

Both modes use an explicit palette for every current canonical category, independent
of document/UI language and checkpoint. This is the application's consistent
convention, not a universal biomedical NER color standard. Familiar aliases map to
the canonical color. Display aliases now cover all54 original model labels in the
catalog and accented/BIO variants. The ambiguous raw PROFESION display alias uses
the profession color; canonical ANONYMIZATION remains distinct. Unknown categories
receive a deterministic color from24 extension palettes instead of all sharing
gray. These finite palettes may reuse colors; literal labels/IDs stay authoritative.
No display alias changes stored scientific labels, model mappings or exports. Existing
scientific consolidation remains the sole duplicate-vote rule.

This is a BRAT-inspired read-only span viewer; it does not embed the BRAT editor
or infer relation arcs. BRAT TXT/ANN exports remain available. See the concrete
[overlap review and captures](OVERLAP_REVIEW.md).

Entity-type toggles and surface search only filter the current drawing/list.
Previous/next annotation navigates that filtered list. Text search uses a private whole-document endpoint and jumps to a fragment
containing the match; returned positions remain absolute. Long documents can be explored using previous/next fragments;
there is no silent document truncation. A long surface is shortened only in the
mention-list preview (ellipsis), while selection details and JSON retain it.

Tests exercise every annotation's selected state in Chromium, including equal
boundaries, crossing and four active annotations, at 320/375/390/768/1024/1440/
1920/2560px. Pure segment tests also verify exact text reconstruction and lanes.
Distinct canonical categories and offsets are never merged or approximately repositioned.

V3 preserves this renderer and adds a synchronized paged Entity/Label/Start/End/
Confidence/Model table. Both selection routes use the same annotation IDs and
highlight all fragments. Version/overlap peers are visible without relying on
color. A mobile bottom-sheet action uses native dialog focus/close semantics.
The renderer benchmark and its limited interpretation are in PERFORMANCE_V3.md.

Catalog correction: before drawing, exactly equal document/canonical-category/
offset mentions from several models consolidate into one annotation ID. All
original labels, models, versions and individual scores remain in `sources` and
are shown in the desktop inspector/mobile sheet. This removes duplicate votes
without changing the sweep algorithm or suppressing distinct legitimate overlaps.
