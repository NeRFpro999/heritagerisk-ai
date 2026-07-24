# HeritageRisk AI — YICTE Product Description

A fresh Python 3.12 audit on 24 July 2026 verified `220 passed, 538 warnings`
with `cd backend && AZURE_OPENAI_ENABLED=false pytest -q`; elapsed time varies
by host and load.

## What the Product Does

HeritageRisk AI is a local web app for visible heritage-site risk triage. It is
built with FastAPI, SQLAlchemy, SQLite, Jinja2, vanilla CSS, Pillow, and pytest.
It is designed as a student competition prototype, not as a production public
service.

The implemented workflow is:

1. A public contributor submits one to six photos, notes, visible-damage tags,
   and severity. Public submissions enter the human review queue as `Pending`.
2. Every uploaded JPEG, PNG, or WEBP file is checked by file signature and size,
   decoded with Pillow, orientation-corrected, and re-encoded without EXIF/GPS
   metadata before storage.
3. An authenticated reviewer signs in with the configured reviewer credential,
   opens the review queue, and approves, rejects, or marks submissions sensitive.
4. Approved observations can be analyzed by mock AI by default, or Azure OpenAI
   when explicitly enabled and configured.
5. The AI proposal uses schema v2 for per-indicator evidence, image references,
   confidence, and evidence sufficiency. Invalid Azure v2 payloads are preserved
   as failed validation states rather than being treated as successful results.
6. The primary AI-review page displays contributor-original, current reviewed,
   and AI-proposed values and offers accept, edit, and reject controls. Not
   every authenticated finalization POST requires explicit per-indicator
   decisions.
7. Finalized Risk Cases store an application-level write-once evidence and
   scoring snapshot. Case pages and Markdown/HTML reports render from that
   snapshot so later edits through the live Observation routes do not change
   the displayed final score breakdown. The database does not enforce
   immutability of the JSON column or referenced image files.
8. Reviewer status changes through the normal status-update route follow the
   enforced transition graph: Draft → Needs Review; Needs Review → Verified or
   Draft; Verified → Routed or Needs Review; Routed → Closed. `Routed` requires
   a destination, and accepted transitions create `CaseEvent` history rows.
   Demo seeding can create cases directly in later statuses without transition
   events.

## Product Evidence in Code

- Multi-image submissions are represented by `ObservationImage` rows.
- The legacy single-image site upload route and template were removed.
- Reviewer actions use signed sessions and CSRF-protected forms.
- Public submission remains unauthenticated by design.
- Reviewer and finalizer identities are recorded as the configured reviewer
  identity, copied into the Risk Case snapshot, and rendered in case/report
  views.
- Mock analysis remains available offline and is always labelled `mock`.
- Generated reports include the required visible-risk triage safety statement.

## Current Boundaries

The app does not provide production security. It has one shared reviewer
credential, not individual accounts or roles. There is no login throttling,
password recovery, HTTPS deployment, private media delivery, malware scanning,
retention policy, or backup/recovery process.

Sensitive image, note, and tag evidence is redacted in selected views, although
observation metadata can remain visible and uploaded file URLs plus read-only
case/report pages are public to anyone who knows the URL.

The audit trail is partial. Status transitions are evented, and new review and
finalization identities are recorded, but there is no complete append-only log
for every edit, every AI rerun, or every report regeneration.

Live Azure behavior is implemented and mock-tested, but no live Azure analysis
result is committed as evidence.

Risk scoring is an explainable heuristic. It is not a validated conservation
risk model, probability, structural-safety assessment, or professional
recommendation.

## Planned, Not Implemented

- Individual reviewer accounts and roles.
- Private media delivery for sensitive uploads.
- Full append-only audit history for every edit and AI attempt.
- Production deployment, HTTPS, backups, rate limiting, monitoring, malware
  scanning, and retention workflows.
- Validated risk weights and thresholds based on expert or outcome evidence.
