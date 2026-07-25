# HeritageRisk AI — Project Charter

## Purpose

HeritageRisk AI helps document visible deterioration evidence at heritage sites and turn it into a human-reviewed Risk Case.

The project is designed for a student competition context. Public submissions
enter `Pending`; authenticated reviewer actions approve evidence before AI and
finalize AI output before a Risk Case is created. The old site-observation upload
route has been removed. A compatibility case-creation POST remains but is
reviewer-authenticated, CSRF-protected, and identity-stamped.

## Primary Implemented Workflow

```text
Site
  -> Observation with multiple images, notes, tags, and severity
  -> Human Review Queue
  -> AI Analysis after approval
  -> Human AI Review and finalization
  -> Risk Case with explainable score
  -> Evidence Report
  -> Manual status/routing update
```

## What the System Does

- Stores heritage sites and observations.
- Supports multiple images for one observation.
- Validates JPEG/PNG/WEBP suffixes against file signatures and uses Pillow to
  preserve EXIF orientation while re-encoding without source metadata.
- Holds public submissions in a `Pending` human review state.
- Authenticates reviewer actions with one environment-configured, scrypt-hashed
  credential and an eight-hour signed session.
- Protects every state-changing form POST with a double-submit CSRF token.
- Lets a reviewer mark an observation as `ApprovedForAI`, `Rejected`, or `Sensitive`.
- Blocks AI analysis unless a human reviewer has approved the observation.
- Uses Azure OpenAI Vision when configured, with a mock fallback that works offline.
- Records an operational Azure failure with a fixed sanitized diagnostic before
  storing the separate labelled mock fallback.
- Sends all approved observation images plus reviewed site context to the analyzer.
- Preserves contributor-original notes, tags, severity, and submission time separately from the editable reviewer working copy and AI proposal.
- Lets a reviewer compare the AI proposal, edit the final accepted values, or reject the proposal before creating a Risk Case.
- Hides observations marked `Sensitive` from general evidence views, without access-controlling the underlying upload URL.
- Calculates risk with a transparent rule-based score: `sum(tag weights) * severity`, capped at 100.
- Snapshots site details, reviewer-final values, and exact scoring arithmetic when a Risk Case is created.
- Records the submission reviewer and Risk Case finalizer, copies both identities
  into the immutable snapshot, and shows them on case and report views.
- Generates Markdown and HTML evidence reports using the snapshot for site/observation evidence and scoring, while showing the current case status and recorded routing destination. Reports include captured image references, audit details, limitations, and the safety notice; contributor-original note text stays in reviewer comparison views and is withheld from reports after privacy review.

## What the System Does Not Do

HeritageRisk AI does **not** auto-route official reports.

The app may record a human-entered routing destination, such as `Local Council`, in the Risk Case and evidence report. That is a documentation field, not an automated dispatch system. No email, notification, external submission, or official escalation is triggered by the app.

HeritageRisk AI also does **not** diagnose structural failure.

The AI is used strictly to draft visible-risk triage evidence. It must not decide whether a site is safe, confirm structural damage, replace a conservator or engineer, or make an emergency, legal, cultural heritage, or conservation authority decision.

Upload normalization does not make media private or prove files malware-free.
The current static upload URLs are public to anyone who obtains them, and
consent, cultural-sensitivity, retention, and cloud-transfer rules remain human
governance responsibilities.

## Responsible AI Principles

1. **Human review before AI**
   Public observations start as `Pending`. AI analysis can run only after a reviewer marks the observation `ApprovedForAI`.

2. **Human finalization on the primary Risk Case route**
   AI output is not final. The primary route lets the reviewer edit the final accepted fields or reject the unchanged AI proposal, then confirm final tags, severity, summary, next step, and any recorded routing destination. The compatibility case route remains authenticated and identity-stamped but does not present the comparison form.

3. **Rule-based scoring**
   The risk score is explainable and deterministic. It is calculated from finalized tags and reviewer-selected severity, not from hidden AI reasoning. The inputs, weights, multiplier, equation, capped score, and band are stored on the Risk Case and are not recalculated from later Observation edits.

4. **No safety decisions**
   The app records visible-risk evidence only. It does not advise entry, repair, cleaning, emergency action, or professional safety conclusions.

5. **Offline demonstrability**
   The mock analyzer remains available so the project can be demonstrated and tested without credentials or network access.

## In Scope

- FastAPI web app with server-rendered Jinja2 pages.
- SQLite persistence for local demo and judging.
- Multi-image observations.
- Content-validated, orientation-normalized, metadata-free image storage.
- Human review queue.
- Minimal reviewer login/logout, signed session, route guards, and CSRF protection.
- Reviewer/finalizer identity fields and immutable report snapshots.
- Azure OpenAI Vision integration with mock fallback.
- AI review result page and human finalization form.
- Explicit AI-draft rejection and rerun path.
- Manual case status update page.
- Rule-based explainable scoring.
- Markdown and HTML evidence reports.
- pytest coverage for routes, workflow gates, reports, scoring, and seed data.

## Out of Scope

- Automatic routing of official reports.
- Structural safety diagnosis.
- Emergency, legal, engineering, or conservation authority decisions.
- Individual user accounts, multiple reviewers, or role-based authorization.
- Password reset/recovery, login throttling, and production identity management.
- Public campaign management.
- Cloud deployment.
- Email, SMS, or external notification integrations.
- A mobile app.
- A frontend framework or second database engine.

The current access control is intentionally limited to one shared reviewer
credential. It does not identify separate people who share that credential, and
there is no append-only action log or per-status updater identity. The local
server uses HTTP, so its session cookie is not marked `Secure`; uploaded media
and read-only case/report pages remain public. The build is therefore a local
competition demonstration, not a production public reporting service.

## Technical Principles

- Keep the app readable for a student project team.
- Preserve the working MVP workflow at every step.
- Use the existing stack: FastAPI, SQLAlchemy, SQLite, Jinja2, vanilla CSS.
- Keep Azure optional and the mock fallback wo