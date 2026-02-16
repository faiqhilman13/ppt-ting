# ASEAN Enterprise Scale Execution Plan

Status date: February 15, 2026  
Scope: Backend, worker, renderer services, platform, security, enterprise integration  
Objective: Make PPT Ting ready for enterprise production use across ASEAN at high concurrency.

## 1. Target Operating Profile

1. Launch posture: Enterprise-first.
2. Deployment posture: Single primary ASEAN region with warm DR in a second region.
3. Security posture: Enterprise baseline in phase 1, compliance hardening in later phases.
4. Tenancy posture: Logical multi-tenant with strict tenant isolation at API, job, and data layers.
5. Identity posture: OIDC SSO first (Okta/Azure AD), SCIM in later phase.

## 2. Current Gaps to Close

1. Storage/DB are local-dev oriented (`sqlite`, local `/storage` files).
2. No first-class auth, RBAC, or tenant isolation in API and job execution.
3. No idempotency layer for generate/revise requests.
4. Observability is improved but not yet SLO-grade (metrics/tracing/alerts/runbooks).
5. Reliability controls need production hardening (DLQ pattern, failover drills, circuit breaking).

## 3. Program Structure

1. Phase 0: Readiness and architecture decisions (1-2 weeks).
2. Phase 1: Secure multi-tenant foundation (4-6 weeks).
3. Phase 2: Reliability, HA, and DR operations (4-6 weeks).
4. Phase 3: Enterprise integration and governance operations (4-6 weeks).

## 4. Phase 0 - Readiness and Design Lock

### Entry Criteria

1. Team alignment on target operating profile.
2. Engineering owners assigned for backend, platform, security, and frontend.
3. Delivery environment available for staging and production.

### Execution Steps

1. Freeze architecture decisions in docs.
   - Update `docs/ARCHITECTURE.md` with target deployment topology and trust boundaries.
   - Add threat model section for auth, upload, storage, and external provider calls.
2. Create environment matrix and release gates.
   - Define `dev`, `staging`, `prod-primary`, `prod-dr`.
   - Define mandatory promotion checks: integration tests, security checks, migration checks.
3. Prepare infrastructure-as-code skeleton.
   - Create IaC repo or `/infra` folder for Kubernetes, managed DB, managed Redis, object storage.
   - Define naming conventions and secrets paths.
4. Define SLOs and capacity targets.
   - API availability SLO.
   - Job success-rate SLO.
   - P95 generation latency SLO by slide-count band.
5. Baseline non-functional test plan.
   - Load profile, failover profile, and security profile test definitions.

### Exit Criteria

1. Architecture decisions approved by engineering and security stakeholders.
2. SLO and capacity targets documented and signed off.
3. IaC skeleton and environment matrix committed.

## 5. Phase 1 - Secure Multi-Tenant Foundation

### Goal

Implement tenant-aware auth, RBAC, idempotency, and production-ready data/storage foundations.

### Execution Steps

1. Add identity and auth context.
   - Add new module: `backend/app/services/auth.py`.
   - Implement JWT/OIDC token validation and auth context extraction.
   - Add tenant and user context dependency in FastAPI routes.
   - Add local-dev bypass mode guarded by explicit config flags.
2. Implement RBAC primitives.
   - Define roles: `org_admin`, `editor`, `viewer`, `service`.
   - Add authorization checks to generation, revision, template management, and download endpoints.
   - Return consistent authorization errors and audit records.
3. Introduce tenant-aware data model.
   - Add `tenant_id` to: `templates`, `document_assets`, `decks`, `deck_versions`, `deck_jobs`, `deck_outlines`, `job_events`, `tool_runs`, `quality_reports`.
   - Add `created_by` where relevant for audit attribution.
   - Add indexes on `(tenant_id, created_at)` and `(tenant_id, id)` patterns.
4. Add idempotency keys for generate/revise.
   - Add new table: `idempotency_keys`.
   - API behavior:
     - Accept `Idempotency-Key` header.
     - Hash request body + route + tenant + actor.
     - Return existing job/deck response for duplicate in-flight or completed requests.
   - Apply to:
     - `POST /api/decks/generate`
     - `POST /api/decks/{deck_id}/revise`
5. Migrate from local SQLite to managed Postgres-compatible path.
   - Add migration framework (Alembic or equivalent).
   - Create initial baseline migration from current schema.
   - Add data migration script for local-to-postgres bootstrap.
6. Replace local artifact dependence with object storage abstraction.
   - Add storage adapter layer in `backend/app/storage.py`.
   - Support `local` and `object_store` backends via config.
   - Store manifests, citations, outputs, and uploads in object storage path format.
7. Secure upload pipeline.
   - Add file size/type hard limits.
   - Add malware scanning integration hook.
   - Reject unsupported content signatures (not only by file extension).
8. API scoping and pagination hardening.
   - Enforce tenant scoping in list/read endpoints.
   - Add cursor pagination for job events and deck lists.

### Repo Touchpoints (Planned)

1. `backend/app/main.py`
2. `backend/app/models.py`
3. `backend/app/schemas.py`
4. `backend/app/db.py`
5. `backend/app/tasks.py`
6. `backend/app/services/auth.py` (new)
7. `backend/app/storage.py`
8. `backend/.env.example`
9. Migration scripts directory (new)

### Phase 1 Verification

1. Unit/integration tests for auth and tenant scoping.
2. Idempotency tests for duplicate generate/revise requests.
3. Migration tests from clean and upgraded databases.
4. Tenant isolation tests (cross-tenant access must fail).
5. Storage backend tests for local and object modes.

### Exit Criteria

1. All generation/revision APIs require auth context in staging.
2. Tenant isolation is enforced in reads and writes.
3. Idempotency is active and verified under retry/replay.
4. Staging runs on Postgres-compatible DB and object storage backend.

## 6. Phase 2 - Reliability, HA, and DR

### Goal

Harden async workflow reliability, autoscaling, and disaster recovery readiness.

### Execution Steps

1. Queue and worker reliability hardening.
   - Tune Celery broker/backend settings for durability and visibility timeouts.
   - Add explicit safe retry semantics and poison-job handling strategy.
   - Add dead-letter queue handling pattern and operator playbook.
2. Introduce circuit breakers and timeout governance.
   - Wrap provider and renderer calls with bounded retries and exponential backoff.
   - Add circuit-open behavior for sustained provider failures.
   - Add fallback behavior classification (recoverable vs terminal).
3. Add horizontal scaling and queue-aware autoscaling.
   - Deploy on Kubernetes.
   - Configure HPA for backend and worker from CPU + queue depth.
   - Configure PodDisruptionBudget and readiness/liveness probes.
4. Strengthen observability to SLO level.
   - Add OpenTelemetry tracing for request-to-job-to-render path.
   - Add metrics dashboards:
     - queue depth
     - job wait time
     - job runtime percentiles
     - provider latency/error rate
     - render failure rate
5. Implement DR execution plan.
   - Configure secondary region with warm stack and replicated backups.
   - Define RTO/RPO targets and recovery runbook.
   - Execute and record at least one failover drill.

### Repo/Platform Touchpoints (Planned)

1. `backend/app/tasks.py` (retry/circuit semantics, error typing)
2. `backend/app/services/*` provider clients (timeouts/retry strategy)
3. Deployment manifests/Helm charts (new)
4. Observability config and dashboards (new)
5. Runbooks under `docs/` (new)

### Phase 2 Verification

1. Load tests with burst job submission and sustained mixed traffic.
2. Chaos tests for provider outages and worker restarts.
3. DR failover drill with measured RTO/RPO.

### Exit Criteria

1. Reliability SLOs met in staging under load profile.
2. Provider/renderer failures degrade gracefully without runaway retries.
3. DR failover procedure validated and repeatable.

## 7. Phase 3 - Enterprise Integration and Governance Operations

### Goal

Add enterprise lifecycle integration and governance operations required by larger customers.

### Execution Steps

1. Add SCIM provisioning.
   - User and group provisioning endpoints.
   - Group-to-role mapping for tenant RBAC.
2. Strengthen audit and compliance operations.
   - Immutable security event stream for auth, admin actions, downloads, revisions.
   - Audit export endpoints and retention policy controls.
3. Add tenant governance controls.
   - Per-tenant quotas for jobs/day, concurrent jobs, upload sizes.
   - Budget guardrails for provider usage and alerts.
4. Add customer-facing operational controls.
   - Service status endpoint with dependencies.
   - Admin controls for throttling and queue pause/resume by tenant.
5. Expand platform policy pack.
   - Secret rotation policy.
   - Backup validation schedule.
   - Vulnerability management cadence.

### Phase 3 Verification

1. SCIM integration test with at least one enterprise IdP.
2. Audit export correctness and completeness tests.
3. Quota and throttling behavior tests under abuse scenarios.

### Exit Criteria

1. Enterprise customer onboarding can be completed with OIDC + SCIM + RBAC.
2. Audit, quota, and governance controls are production-operational.
3. Compliance-readiness evidence package is available.

## 8. Cross-Phase Non-Negotiables

1. Every phase must ship with runbooks and rollback steps.
2. Every phase must include performance and security validation.
3. No schema change ships without migration + rollback + backward-compat check.
4. No new critical path dependency ships without timeout and retry policy.

## 9. Suggested Ticket Breakdown Template

Use this ticket template for every work item:

1. Problem statement.
2. Scope in/out.
3. API/schema changes.
4. Data migration strategy.
5. Rollback plan.
6. Test plan.
7. Observability updates.
8. Security impact.
9. Acceptance criteria.

## 10. Delivery Governance

1. Weekly architecture review for cross-cutting changes.
2. Weekly security review for auth, storage, and external call surfaces.
3. End-of-phase go/no-go review using exit criteria in this document.

## 11. Immediate Next Actions

1. Approve this document as the source execution plan.
2. Convert Phase 1 steps into sprint tickets with owners and estimates.
3. Implement Phase 0 artifacts first, then begin Phase 1.

