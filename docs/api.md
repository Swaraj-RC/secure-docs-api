# API Reference

Base URL: `/api/v1`

## Error Response Format

All errors follow this envelope:

```json
{
  "error": {
    "code": "STABLE_UPPER_SNAKE_CODE",
    "message": "Human readable description",
    "details": [
      {"field": "email", "issue": "Already registered"}
    ],
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTHENTICATION_REQUIRED` | 401 | Missing or invalid access token |
| `TOKEN_EXPIRED` | 401 | Access token has expired |
| `INVALID_REFRESH_TOKEN` | 401 | Refresh token invalid or revoked |
| `REFRESH_TOKEN_REUSED` | 401 | Refresh token reuse detected; family revoked |
| `FORBIDDEN` | 403 | Authenticated but insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found (or hidden from non-members) |
| `CONFLICT` | 409 | Resource already exists (duplicate email, membership, etc.) |
| `VALIDATION_ERROR` | 422 | Request body/params failed validation |
| `RATE_LIMITED` | 429 | Too many requests |
| `ACCOUNT_LOCKED` | 423 | Account locked due to failed login attempts |
| `INVALID_CREDENTIALS` | 401 | Wrong email or password |
| `PASSWORD_TOO_WEAK` | 422 | Password does not meet policy |
| `FILE_TOO_LARGE` | 413 | Upload exceeds size limit |
| `FILE_TYPE_NOT_ALLOWED` | 422 | MIME type not in allowlist |
| `FILE_TYPE_MISMATCH` | 422 | Declared MIME does not match magic bytes |
| `INTERNAL_ERROR` | 500 | Unexpected server error (ref request_id) |

## Endpoints

### Health
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/healthz` | No | Liveness probe |
| GET | `/readyz` | No | Readiness probe (checks DB + storage) |

### Auth
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Create account |
| POST | `/auth/login` | No | Get access + refresh tokens |
| POST | `/auth/refresh` | No | Rotate refresh token |
| POST | `/auth/logout` | Yes | Revoke refresh token |
| GET | `/auth/me` | Yes | Get current user |

### Users
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/users/me` | Yes | Get own profile |
| PATCH | `/users/me` | Yes | Update own profile |
| POST | `/users/me/password` | Yes | Change password |

### Workspaces
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/workspaces` | Yes | Create workspace |
| GET | `/workspaces` | Yes | List my workspaces |
| GET | `/workspaces/{ws_id}` | Yes | Get workspace |
| PATCH | `/workspaces/{ws_id}` | Yes | Update workspace |
| DELETE | `/workspaces/{ws_id}` | Yes | Delete workspace (owner only) |

### Members
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/workspaces/{ws_id}/members` | Yes | List members |
| POST | `/workspaces/{ws_id}/members` | Yes | Add member |
| PATCH | `/workspaces/{ws_id}/members/{user_id}` | Yes | Change role |
| DELETE | `/workspaces/{ws_id}/members/{user_id}` | Yes | Remove member |

### Documents
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/workspaces/{ws_id}/documents` | Yes | Create document |
| GET | `/workspaces/{ws_id}/documents` | Yes | List documents (filtered, sorted, paginated) |
| GET | `/documents/{doc_id}` | Yes | Get document |
| PATCH | `/documents/{doc_id}` | Yes | Update document |
| DELETE | `/documents/{doc_id}` | Yes | Soft delete |
| POST | `/documents/{doc_id}/restore` | Yes | Restore (admin+) |

### Versions
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/documents/{doc_id}/versions` | Yes | Upload new version |
| GET | `/documents/{doc_id}/versions` | Yes | List versions |
| GET | `/documents/{doc_id}/versions/{vid}/download` | Yes | Download file |
| DELETE | `/documents/{doc_id}/versions/{vid}` | Yes | Delete version (admin+) |

### Shares
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/documents/{doc_id}/shares` | Yes | List shares |
| POST | `/documents/{doc_id}/shares` | Yes | Create share |
| DELETE | `/documents/{doc_id}/shares/{sid}` | Yes | Revoke share |

### Audit
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/workspaces/{ws_id}/audit-logs` | Yes | Query workspace audit logs |
| GET | `/audit-logs/me` | Yes | My audit trail |
