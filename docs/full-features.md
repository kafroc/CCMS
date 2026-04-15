## Detailed feature reference

The following sections describe, page-by-page and capability-by-capability, what the system currently supports.

### 1. Login, accounts, and permission control

- Username/password login with JWT-based API authentication.
- Endpoint-level permission checks and per-TOE access control on the backend.
- Two role tiers: `admin` and regular user.
- Administrators can create users, reset or change passwords, and delete users.
- Administrators can grant per-TOE `read` or `write` permissions to regular users; administrators have read/write permission on all TOEs by default.
- Forced password change on first login.

### 2. TOE management

- Create, edit, and delete TOEs, and filter/browse them by name and type.
- Basic TOE information includes version, product summary, TOE type description, and more.
- The TOE detail page organizes Overview, Assets, TOE documents, and ST/PP documents into separate tabs — structured data and evidence artifacts live in the same context.
- `AI Consolidate` can condense a whole description (typically used after extracting content from ST/PP documents), and per-field AI completion is also supported.
- Chinese fields can be translated into English in bulk — convenient for preparing an English-language ST draft.
- A single TOE can be exported as a bundle and re-imported, making cross-environment migration, backup, or demo-data distribution straightforward.

### 3. Assets and supporting materials

- Build an asset inventory per TOE, with fields like name, type, importance, etc.
- Assets feed directly into threat identification and completeness analysis.
- Upload product manuals, design documents, reference materials, ST/PP documents, and more.
- Upload processing status is tracked so you can tell "parsed", "parsing", and "failed" apart.
- Uploaded files are persisted uniformly under `storage/`, with extension whitelisting, filename sanitization, and path-traversal protection.
- TOE documents and ST/PP documents are managed separately, cleanly splitting "product materials" from "reference / baseline materials".

### 4. Threat / Assumption / OSP and SPD management

- The Threat page has four core areas: `Threats`, `Assumptions`, `OSPs`, `Completeness`.
- Threats capture threat ID, threat agent, adverse action, affected assets, consequence, and risk level.
- Threats support confirm, rollback, mark-as-false-positive, batch confirm, batch delete, and manual override of risk level.
- Assumptions and OSPs have their own create / edit / delete / confirm / reject / rollback and batch confirm/reject workflows.
- Threats, Assumptions, and OSPs can all be mapped onto downstream Security Objectives, preserving a clear lineage from security problem to objective.
- Threat completeness analysis scores and flags issues along several dimensions: asset coverage, objective mapping, SFR mapping, test coverage, residual risk, and reference-document alignment.
- A per-asset "ignore" switch is available for weakly-covered assets, so items that are known to be out of scope do not keep polluting the completeness score.

### 5. ST reference material and document import

- Upload existing ST reference documents and extract structured content: Threats, Objectives, SFRs, Assets, etc.
- Reference materials support re-parse retry, deletion, and a share toggle for team-wide reuse.
- Threats can be imported from documents; Security Objectives can also be imported from ST/PP documents.
- This is intended for turning historical project experience into candidate items for the current project, rather than starting from zero each time.

### 6. Security objectives and SFR management

- The Security page has four core areas: `Objectives`, `SFRs`, `Completeness`, `SFR Library`.
- Security Objectives support create, edit, delete, confirm, reject, and rollback.
- Each Objective exposes its source mappings — it is clear whether it is derived from a Threat, Assumption, or OSP.
- Source mappings can be edited manually, including unlinking, making review-time fine-tuning easy.
- AI can recommend security objectives, and objectives can also be imported from ST/PP documents.
- SFR instances support create, edit, delete, confirm, reject, and rollback, and can be mapped to one or more Objectives.
- Supported operations: auto-match SFRs to Objectives, AI-completion of SFR content, automatic dependency resolution, and ST/PP consistency checks.
- At export time, SFR dependency chains are followed automatically to produce more complete output.

### 7. SFR library management

- The SFR Library is a first-class page in the system — not just for browsing standard entries, but for maintenance and governance as well.
- Supports paginated search, edit, delete, and batch delete.
- CSV import is supported for bulk-loading or correcting the company's internal SFR library.
- Dependency fields are normalized on the backend — only standardized SFR IDs are kept, while `AND/OR` logic is preserved.
- This library can serve both as a canonical reference and as a team-tailored operational knowledge base.

### 8. Test case management

- The Tests page has two regions: the test list, and the completeness check.
- Test cases support create, edit, delete, and fields for test ID, name, objective, target under test, scenario, prerequisites, steps, expected results, and so on.
- A single test case can be linked to multiple SFRs.
- Test types are `coverage`, `depth`, and `independent` — and they can be combined.
- Individual cases support confirm / reject / rollback; batch confirm and batch delete are also available.
- AI can batch-generate test cases across the current SFR set, with in-page progress feedback on the task.
- The test completeness report analyzes how current tests cover the SFRs, helping you locate gaps.

### 9. Risk dashboard and assurance-chain analysis

- The Risk page is not a plain statistics page — it is a centralized health check of the current TOE's modeling quality.
- The dashboard shows an Assurance Maturity score that aggregates Threat completeness, Security completeness, Test completeness, and other dimensions into an overall value.
- An Assurance Chain visualization shows, in chain form, the strength of the hand-off from security problems → objectives → SFRs → tests.
- An Assurance Tree gives a hierarchical view that makes it obvious which layer is the weakest.
- Blind Spots detection identifies possible omissions across assets, Threats, Objectives, SFRs, and Tests, with a confidence score for each.
- Additional analysis includes risk distribution, residual-risk status, a completeness radar chart, key findings, and an AI-generated summary.
- Per-Threat residual-risk dispositions can be recorded (accept, mitigate, transfer, avoid).

### 10. AI models and AI-assisted capabilities

- Every user can configure their own AI model — there is no hard dependency on any single vendor.
- Any OpenAI-compatible service works: OpenAI, Ollama, vLLM, or any self-hosted equivalent.
- Supports create, edit, delete, connectivity validation, and setting the current working model.
- API keys are stored encrypted on the backend — they are never persisted in plaintext.
- A per-model chat window is provided so you can do a quick sanity check right after integration.
- AI capabilities currently wired into the business workflow include:
  - TOE description drafting and field consolidation
  - Asset suggestions
  - Document analysis
  - Threat scanning
  - Assumption / OSP suggestions
  - Security Objective suggestions
  - SFR matching and completion
  - Test case generation
  - English translation
  - Risk summary and blind-spot suggestions
- All long-running AI operations report progress through task-status polling, so the page never hangs indefinitely.

### 11. Export, templates, and delivery

- The Export page follows a preview → edit → export flow.
- ST documents can be exported in both Markdown and Word (`.docx`) formats.
- Markdown can be edited directly before export — ideal for final polish on top of the system-generated draft.
- ST templates are managed centrally in Settings; a set of placeholders is supported for mapping TOE, assets, Threats, objectives, SFRs, tests, and more.
- Templates can be loaded from files and the current template can be saved back to file, making team-wide template sharing easy.

### 12. Settings, logging, and system operations

- The Settings page currently groups language switching, AI models, user management, system parameters, log viewing, and ST template maintenance.
- The UI supports both Chinese and English — a good fit for teams that model in Chinese but deliver in English.
- Administrators can configure the PDF parsing timeout, reducing failure rates on large documents.
- Audit logs and error logs can be queried and cleaned from the UI — easy to trace who changed what at which time, and what exceptions the service produced during runtime.
- Audit logs record user, resource, IP, status code, latency, and other key fields.

### 13. Security and engineering details

- The backend applies basic safety controls to upload paths, filenames, and extensions to reduce path-traversal and malicious-file risk.
- API responses use a uniform structured format so the frontend can handle them stably.
- In production, the database, Redis, backend, worker, and frontend services can all be brought up via Docker Compose.
- Data such as `storage/` and `ST Template.md` is preserved via volume mounts for proper persistence.
- The project ships with backend test cases covering authentication, configuration, encryption, health checks, logging, system settings, TOE handling, and upload security.