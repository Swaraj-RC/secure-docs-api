# ADR-0005: Append-Only Audit Trail Architecture and Immutability Guarantees

## Context
A core requirement of document and records management systems is compliance auditing. Regulatory standards require that document creations, revisions, downloads, deletions, and ACL modifications leave an indelible, tamper-evident trail. The audit records must be immutable, queryable across workspaces and actors, and prevent leakage of tenant boundaries.

## Decision
We implement a dedicated `audit_logs` table and a centralized `record_audit_event` service:

1. **Schema & Immutability:**
   - Table columns: `id` (UUID), `workspace_id`, `actor_id`, `action`, `resource_type`, `resource_id`, `ip_address`, `user_agent`, `metadata` (JSONB), and `created_at` (TIMESTAMPTZ).
   - No `updated_at` column exists.
   - The ORM and API expose zero update or delete operations on audit logs.
   - `actor_id` references `users(id)` with `ON DELETE RESTRICT` to ensure actor provenance cannot be destroyed.
   - `workspace_id` cascades only on complete tenant deletion.

2. **Atomic In-Transaction Logging:**
   - Audit events are written to the database session in the same unit of work as the resource mutation.
   - This prevents dual-write anomalies (e.g. state updated but event lost, or event logged but transaction rolled back).

3. **Performance & Partitioning Readiness:**
   - Composite indexes: `ix_audit_workspace_created (workspace_id, created_at DESC)`, `ix_audit_actor (actor_id, created_at DESC)`, and `ix_audit_resource (resource_type, resource_id)`.
   - The schema is designed to allow transparent PostgreSQL range partitioning by `created_at` (e.g. monthly tables) in high-throughput production deployments.

4. **Access Control & Multi-Tenancy:**
   - `GET /workspaces/{ws_id}/audit-logs`: Restricted to workspace `owner` and `admin` roles. Non-members receive a 404 (leakage prevention rule), while regular members and viewers receive 403 Forbidden.
   - `GET /audit-logs/me`: Allows any authenticated actor to inspect their own activity history across workspaces.

## Consequences
- Every document mutation, version download, share grant, and membership change writes an audit record.
- Storage overhead scales with system activity; production deployments should enable table partitioning and cold retention archival.
