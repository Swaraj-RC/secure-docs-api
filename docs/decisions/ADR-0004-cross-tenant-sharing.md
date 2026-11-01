# ADR-0004: Cross-Tenant Document Sharing Policy

## Status
Accepted

## Context
A key requirement in document records management is sharing specific records with external collaborators, auditors, or clients who are not full members of the host workspace tenant. For example, sharing a vendor agreement with legal counsel or an audit report with an external compliance auditor.

We must decide whether `document_shares` permits sharing to users outside the workspace tenant, and how tenant isolation is maintained.

Two models were considered:
1. Strict Intra-Workspace Only: Users can only be granted document shares if they are already active members of the workspace.
2. Controlled Cross-Tenant Sharing: Document shares can be granted to any registered user by email or user ID. An active share grants direct access to the specific document and its versions, but grants zero visibility into the workspace itself or other workspace documents.

## Decision
We adopt Controlled Cross-Tenant Sharing with strict least-privilege scoping:
1. Granters may share documents with any valid registered user by email or user ID.
2. Non-workspace members holding an active (unexpired) share can view (or edit, if granted `write`) the specific document via `/documents/{doc_id}` and download versions via `/documents/{doc_id}/versions/{vid}/download`.
3. Non-workspace members receive `404 Not Found` if they attempt to list documents via `/workspaces/{ws_id}/documents` or inspect workspace metadata via `/workspaces/{ws_id}`.
4. When a share expires (`expires_at < now()`) or is revoked via `DELETE /documents/{doc_id}/shares/{id}`, the external user immediately loses access; subsequent requests return `404 Not Found` (preserving leakage prevention).

## Consequences
- Enables realistic B2B collaboration and external auditing workflows.
- Granter role rules are strictly enforced: ordinary workspace members can grant `read` only; only workspace owners, admins, or document owners can grant `write` access.
- Workspace boundary security is intact because workspace-level endpoints require verified membership.

