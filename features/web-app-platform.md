# Web App Platform (API + Frontend + Credits)

## Goal
Replace Streamlit as the primary user-facing surface with a web app that has auth, credits, and a job queue, suitable for multi-tenant production use (Docker/container deployment).

## Scope
- Backend API (FastAPI/Django REST) for uploads, job creation, status, and artifacts.
- Queue/workers for pipeline execution (reuse existing pipeline code).
- Frontend (Next.js/React or alternative) for login, upload, job configuration, status, and results.
- Credits/billing mechanics and payment provider integration (Stripe/Mollie) via webhooks.
- Storage: S3/MinIO for uploads and artifacts; Postgres for users/credits/jobs; Redis/RabbitMQ for the queue.
- Observability and security baseline (logging, metrics, rate limits, authZ, file guardrails).

## Out of scope (now)
- New pipeline features; we reuse the existing pipeline.
- TTS/audio generation beyond the existing podcast JSON.
- Advanced RBAC/tenant hierarchies; start with basic roles.

## Approach (phases)
1) Foundations
- Finalize stack choices (API, queue, frontend, auth, payment).
- Isolate pipeline into a library call with pluggable storage (local/S3) and configurable I/O paths.
- Docker baselines (API, worker, frontend) + shared env/secret management.

2) API & jobs
- Endpoints: login (OIDC/JWT), upload PDF → object storage, create job (debit credits), job status, artifact listing/download (signed URLs).
- Job runner/worker: fetches PDF + config, runs pipeline, writes outputs to storage and metadata to DB.
- DB models: User, CreditBalance, Job, JobArtifact, PaymentEvent.

3) Frontend MVP
- Pages: login, upload, job configuration (steps/provider/pages), job status/queue, results list, detail/artifact download.
- Polling or websockets for job status.

4) Payments & credits
- Payment provider webhook (Stripe/Mollie) → credit top-up; idempotency keys.
- Admin views: credit adjustments, job history export.

5) Hardening & scale
- Rate limiting, request size limits, PDF sanitization, abuse controls.
- Observability: structured logging, metrics (Prometheus), tracing; alerts.
- Backups and lifecycle policies for object storage; DLQ for failed jobs.

6) Streamlit migration/sunset
- Keep Streamlit for demo/internal testing, but primary path via the web app.
- Shared pipeline service function used by both CLI and worker.

## Acceptance criteria (MVP)
- User can log in, upload a PDF, start a job, view status, and download artifacts via browser.
- Credits are debited at job start; no job without sufficient credits.
- Jobs run in a worker/queue (not in the web process) and store artifacts in object storage.
- All endpoints are secured; uploads/downloads are tenant/user isolated (no cross-user leaks).
- Basic observability: request logs, job logs, and simple metrics (jobs succeeded/failed, queue depth).

## Risks / watchouts
- LLM cost and latency; need caching/retry policy.
- PDF uploads/storage: compliance/PII; sanitization and retention policy.
- Payment/webhook robustness (idempotency, fraud, double booking).
- Scaling queue/worker vs. API; resource isolation for heavy jobs.

## Open questions
- Stack choices: FastAPI vs Django REST; Celery vs RQ/Arq; Next.js vs simpler HTMX/Jinja.
- Auth: managed OIDC (Auth0/Keycloak/Azure AD) or self-hosted JWT?
- Payment provider: Stripe (international) vs Mollie (NL/EU).
- Hosting: start on single VM/docker-compose or go managed (Cloud Run/App Service/K8s)?
