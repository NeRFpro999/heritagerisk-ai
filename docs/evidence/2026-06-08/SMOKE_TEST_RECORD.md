# Manual Smoke Test Record — MVP Stabilisation

Date: 2026-06-08
Focus: MVP Stabilisation, risk scoring tests, report safety wording, and Azure GPT-5-mini integration with mock fallback.

This record is for manual browser testing. It should be completed while running the HeritageRisk AI FastAPI app locally. Do not mark a mode as passed until the steps have been performed in the browser.

## Environment

- Tester:
- Browser:
- Local app URL:
- Git commit or branch:
- Notes:

## Golden Path Checklist

- [ ] Start app locally.
- [ ] Open dashboard.
- [ ] Open seed/demo site.
- [ ] Create or view a site.
- [ ] Upload an observation image.
- [ ] Add observer notes.
- [ ] Add damage tags.
- [ ] Set severity.
- [ ] Run analysis.
- [ ] Confirm provider label.
- [ ] Create risk case.
- [ ] Update case status.
- [ ] Set routed-to organisation.
- [ ] Open HTML report.
- [ ] Download Markdown report.

Expected golden path result:

The user can move from dashboard to site, observation, analysis, risk case, status update, and report export without a route crash. The AI result remains clearly labelled as mock fallback or Azure, and report wording keeps the safety boundary: HeritageRisk AI is for visible risk triage only and does not replace professional advice or human review.

## Mode A — Mock Fallback

Configuration:

```text
AZURE_OPENAI_ENABLED=false
```

Expected result:

Mock fallback works. The analysis route redirects normally, stores a mock result, and the browser does not show an Azure error or crash page.

Steps:

- [ ] Start app with `AZURE_OPENAI_ENABLED=false`.
- [ ] Open the dashboard.
- [ ] Open or create a site.
- [ ] Upload an observation image.
- [ ] Add notes that include a visible issue, such as a crack, water staining, or erosion.
- [ ] Add damage tags and severity.
- [ ] Run analysis.
- [ ] Confirm the provider label shows mock or fallback wording.
- [ ] Confirm the observation detail page still displays summary, confidence, recommended action, and tags.
- [ ] Create a risk case from the observation.
- [ ] Update status and routed-to organisation.
- [ ] Open the HTML report.
- [ ] Download the Markdown report.

Pass/fail:

- [ ] Pass
- [ ] Fail

Notes:

```text

```

Screenshot filename:

```text

```

## Mode B — Valid Azure GPT-5-mini

Configuration:

```text
AZURE_OPENAI_ENABLED=true
AZURE_OPENAI_ENDPOINT=<local .env value, not recorded here>
AZURE_OPENAI_API_KEY=<local .env value, not recorded here>
AZURE_OPENAI_PRIMARY_DEPLOYMENT=gpt-5-mini
```

Expected result:

Azure analysis succeeds. The provider shows `azure:gpt-5-mini` or `azure:<deployment>`. The route redirects normally and stores the same output shape used by the app: analysis status, summary, confidence, provider, recommended action, and raw JSON response.

Steps:

- [ ] Start app with valid Azure settings.
- [ ] Open the dashboard.
- [ ] Open or create a site.
- [ ] Upload an observation image.
- [ ] Add clear notes, damage tags, and severity.
- [ ] Run analysis.
- [ ] Confirm the route redirects back to the observation detail page.
- [ ] Confirm the provider label shows `azure:gpt-5-mini` or `azure:<deployment>`.
- [ ] Confirm the summary is visible risk triage only and does not claim a final professional decision.
- [ ] Confirm confidence and recommended action display.
- [ ] Create a risk case.
- [ ] Update status and routed-to organisation.
- [ ] Open the HTML report.
- [ ] Download the Markdown report.

Pass/fail:

- [ ] Pass
- [ ] Fail

Notes:

```text

```

Screenshot filename:

```text

```

## Mode C — Wrong Deployment Name

Configuration:

```text
AZURE_OPENAI_ENABLED=true
AZURE_OPENAI_ENDPOINT=<local .env value, not recorded here>
AZURE_OPENAI_API_KEY=<local .env value, not recorded here>
AZURE_OPENAI_PRIMARY_DEPLOYMENT=<intentionally wrong deployment name>
```

Expected result:

Azure fails safely. The analysis route does not crash, the browser does not expose Azure diagnostic details, and the stored provider remains `mock`.

Steps:

- [ ] Start app with Azure enabled and an intentionally wrong deployment name.
- [ ] Open the dashboard.
- [ ] Open or create a site.
- [ ] Upload an observation image.
- [ ] Add notes, damage tags, and severity.
- [ ] Run analysis.
- [ ] Confirm the route redirects back to the observation detail page.
- [ ] Confirm no Azure error details are shown in the browser.
- [ ] Confirm provider label shows mock or fallback wording.
- [ ] Confirm summary, confidence, recommended action, and tags are still stored.
- [ ] Create a risk case.
- [ ] Update status and routed-to organisation.
- [ ] Open the HTML report.
- [ ] Download the Markdown report.

Pass/fail:

- [ ] Pass
- [ ] Fail

Notes:

```text

```

Screenshot filename:

```text

```

## Evidence Summary

- Mode A completed: [ ] Yes [ ] No
- Mode B completed: [ ] Yes [ ] No
- Mode C completed: [ ] Yes [ ] No
- Any route crash observed: [ ] Yes [ ] No
- Any secret or API key visible in browser: [ ] Yes [ ] No
- Any report wording that sounds like professional, legal, emergency, engineering, or conservation advice: [ ] Yes [ ] No

Final tester comment:

```text

```
