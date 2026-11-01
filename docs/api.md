# API Reference & Contracts

## Base URL
All API v1 routes are mounted under `/api/v1`.

## Common Error Envelope (RFC 7807 Inspired)
All errors return consistent JSON envelopes with stable machine-readable codes and request tracing IDs:

```json
{
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "Could not validate credentials",
    "details": [],
    "request_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
  }
}
```

Standard error codes:
- `AUTHENTICATION_REQUIRED` (401)
- `FORBIDDEN` (403)
- `NOT_FOUND` (404)
- `CONFLICT` (409)
- `PAYLOAD_TOO_LARGE` (413)
- `RANGE_NOT_SATISFIABLE` (416)
- `VALIDATION_ERROR` (422)
- `RATE_LIMIT_EXCEEDED` (429)
- `INTERNAL_ERROR` (500)

## Pagination Envelope
List endpoints return paginated responses structured as:
```json
{
  "items": [...],
  "page": 1,
  "size": 20,
  "total": 42,
  "pages": 3
}
```
Query parameters: `page` (default 1) and `size` (default 20, max 100).

## Endpoints Summary

### Authentication (`/api/v1/auth`)
- `POST /register`: Register a new user (`email`, `password`, `full_name`).
- `POST /login`: Authenticate and obtain access token (15m) + refresh token (7d).
- `POST /refresh`: Submit refresh token to obtain a rotated token pair.
- `POST /logout`: Revoke active refresh token.
- `GET /me`: Return authenticated caller identity.

### Workspaces (`/api/v1/workspaces`)
- `POST /`: Create a new workspace (`name`, `slug`).
- `GET /`: List workspaces the caller belongs to.
- `GET /{ws_id}`: Retrieve workspace metadata.
- `PATCH /{ws_id}`: Update workspace name (owner/admin only).
- `DELETE /{ws_id}`: Delete workspace (owner only).
- `GET /{ws_id}/members`: List workspace members (paginated).
- `POST /{ws_id}/members`: Invite/add member (`email`, `role`).
- `PATCH /{ws_id}/members/{user_id}`: Update member role.
- `DELETE /{ws_id}/members/{user_id}`: Remove member or leave workspace.

### Documents (`/api/v1`)
- `POST /workspaces/{ws_id}/documents`: Create document metadata (`title`, `description`, `classification`).
- `GET /workspaces/{ws_id}/documents`: Search, filter, and list documents.
  - Query filters: `q`, `status`, `classification`, `owner_id`, `created_after`, `created_before`, `sort` (`[+/-]created_at`, `title`, `updated_at`).
- `GET /documents/{doc_id}`: Get document metadata.
- `PATCH /documents/{doc_id}`: Update document metadata.
- `DELETE /documents/{doc_id}`: Soft delete document.
- `POST /documents/{doc_id}/restore`: Restore soft-deleted document (owner/admin only).

### Document Versions & Downloads (`/api/v1`)
- `POST /documents/{doc_id}/versions`: Upload new file version (`multipart/form-data`).
- `GET /documents/{doc_id}/versions`: List versions for a document.
- `GET /documents/{doc_id}/versions/{vid}/download`: Download file version. Supports HTTP `Range` requests (`bytes=start-end`) returning `206 Partial Content`.

### Document Sharing (`/api/v1`)
- `POST /documents/{doc_id}/shares`: Grant document access to another user (`user_id` or `email`, `permission`: `read`/`write`, `expires_at`).
- `GET /documents/{doc_id}/shares`: List active shares.
- `DELETE /documents/{doc_id}/shares/{share_id}`: Revoke share.

### Audit Logs (`/api/v1`)
- `GET /workspaces/{ws_id}/audit-logs`: List workspace audit trail (owner/admin only).
  - Query filters: `actor_id`, `action`, `resource_type`, `date_from`, `date_to`.
- `GET /audit-logs/me`: List caller's personal audit activity trail across workspaces.
