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
Two additional annotations on [4,9) remain individually selectable; the region
shows a multiplicity indicator rather than hiding one label behind another.

A greedy interval allocator assigns stable display lanes to intersecting spans.
Lane numbers appear in the alternative mention list. The text uses a soft
highlight with underline and a multiple-annotation count, keeping wrapping and
mobile line height readable instead of stacking an arbitrary number of labels.
Selecting a region opens a button for every covering annotation; selecting one
highlights all its fragments and shows its own label, complete surface, offsets,
model and actual confidence. This works with pointer, touch, Enter or Space.
The mention list provides direct selection without relying on color or hover.

Entity-type toggles and surface search only filter the current drawing/list.
Previous/next annotation navigates that filtered list. Text search uses a private whole-document endpoint and jumps to a fragment
containing the match; returned positions remain absolute. Long documents can be explored using previous/next fragments;
there is no silent document truncation. A long surface is shortened only in the
mention-list preview (ellipsis), while selection details and JSON retain it.

Tests exercise every annotation's selected state in Chromium, including equal
boundaries, crossing and four active annotations, at 320/375/390/768/1024/1440/
1920/2560px. Pure segment tests also verify exact text reconstruction and lanes.
No annotation is deleted, merged across labels or approximately repositioned.

V3 preserves this renderer and adds a synchronized paged Entity/Label/Start/End/
Confidence/Model table. Both selection routes use the same annotation IDs and
highlight all fragments. Version/overlap peers are visible without relying on
color. A mobile bottom-sheet action uses native dialog focus/close semantics.
The renderer benchmark and its limited interpretation are in PERFORMANCE_V3.md.
