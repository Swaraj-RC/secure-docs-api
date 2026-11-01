# ADR-0002: Deny-by-Default Central Policy Layer and Leakage Prevention

## Context

Multi-tenant document management requires fine-grained access control with distinct layers of authority:
1. Workspace roles (Owner, Admin, Member, Viewer).
2. Per-document explicit shares (read/write permissions, optional expiration).
3. Document classification tiers (`public`, `internal`, `confidential`, `restricted`).
4. Document ownership.

Scattering authorization checks across endpoints or service methods risks permission leaks, inconsistent enforcement, and information leakage.

## Decision

1. **Central Pure-Function Policy Layer:** All access decisions are computed exclusively through pure functions in `app/policies/access.py` (`can_view_document`, `can_edit_document`, `can_upload_version`, `can_manage_shares`). No inline authorization checks are permitted in endpoints or services.
2. **Deny-by-Default:** Any action not explicitly permitted evaluates to `False`.
3. **Leakage Prevention (404 vs 403 Rule):**
   - If an actor is not a member of the workspace owning a document, the API returns `404 Not Found` rather than `403 Forbidden`, preventing malicious actors from probing document UUID existence.
   - If an actor is a verified workspace member but lacks permission (e.g. Viewer attempting to edit), the API returns `403 Forbidden`.
4. **Meta-Test Guard:** A security meta-test inspects `app.routes` at test time to assert every non-public route requires authentication.

## Consequences

- **Positive:** Centralized auditability, elimination of IDOR existence probing, guaranteed enforcement across all routes.
- **Negative:** Non-members cannot be distinguished from genuinely non-existent records by design.
