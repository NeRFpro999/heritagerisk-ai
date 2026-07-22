# Screenshot Evidence Checklist — 2026-06-08

These screenshots support the MVP browser smoke test for HeritageRisk AI. Capture them manually while running the local FastAPI app.

Screenshots must not show API keys, `.env` contents, secrets, or private Azure portal pages.

## Required Screenshots

### 01_dashboard.png

What it should show:
The HeritageRisk AI dashboard loaded in the browser, with normal navigation visible and no error page.

Why it matters:
This proves the app starts successfully and the first user-facing page is reachable.

Invalid or confusing if:
The screenshot shows a server error, browser connection error, terminal output, unrelated website, or cropped page with no clear app identity.

### 02_site_detail.png

What it should show:
A site detail page for a demo or manually created heritage site, including site name, location or description, and observation area.

Why it matters:
This proves the site workflow is available before uploading observations.

Invalid or confusing if:
The page is a site list instead of a site detail page, the site name is not visible, or the screenshot does not show enough context to identify the site.

### 03_observation_upload_form.png

What it should show:
The observation upload form with fields for image upload, notes, damage tags, and severity.

Why it matters:
This proves the evidence collection step is available and supports the MVP risk inputs.

Invalid or confusing if:
The form fields are hidden, the image upload control is not visible, or the screenshot shows a submitted result instead of the upload form.

### 04_analysis_mock_disabled_mode.png

What it should show:
An observation analysis result when `AZURE_OPENAI_ENABLED=false`, with the provider labelled as mock or fallback.

Why it matters:
This proves the app works without Azure and the mock fallback path does not crash.

Invalid or confusing if:
The provider label is missing, the page shows an Azure error, or the screenshot does not make it clear that mock/fallback mode was used.

### 05_analysis_azure_enabled_mode.png

What it should show:
An observation analysis result with Azure enabled and valid local settings, with provider shown as `azure:gpt-5-mini` or `azure:<deployment>`.

Why it matters:
This proves the main app can use the Azure GPT-5-mini integration through the browser workflow.

Invalid or confusing if:
The provider is mock, the route failed, raw secrets are visible, or the screenshot includes private Azure portal details instead of the local app result.

### 06_analysis_wrong_deployment_fallback.png

What it should show:
An observation analysis result after using an intentionally wrong deployment name, with the app falling back to mock and still rendering normally.

Why it matters:
This proves Azure failure is handled safely and the route does not crash.

Invalid or confusing if:
The browser shows a traceback, Azure diagnostic details are exposed to the user, or there is no visible mock/fallback result.

### 07_risk_case_detail.png

What it should show:
A risk case detail page created from an analysed observation, including risk score, risk band, status, and linked observation context.

Why it matters:
This proves analysis output can continue into the risk case workflow.

Invalid or confusing if:
The screenshot shows only the observation page, no risk score or band is visible, or the case context is unclear.

### 08_status_update_routed.png

What it should show:
A case detail page after status has been updated and a routed-to organisation has been set.

Why it matters:
This proves the review workflow can track triage status and responsibility.

Invalid or confusing if:
The status did not change, routed-to organisation is blank, or the screenshot does not show the saved case state.

### 09_report_html.png

What it should show:
The HTML report page for the risk case, including the AI/manual analysis summary and safety wording.

Why it matters:
This proves the browser report view is available and uses competition-ready risk communication.

Invalid or confusing if:
The report page is missing key case details, shows unsafe final-advice wording, or displays broken formatting.

### 10_report_markdown_download.png

What it should show:
Evidence that the Markdown report download works, such as the downloaded `.md` file open in the browser or file preview with the report title and case content visible.

Why it matters:
This proves the export path works and produces a usable report artifact.

Invalid or confusing if:
The screenshot shows only a downloads bar with no readable report content, an unrelated file, or a failed download page.
