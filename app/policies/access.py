"""Central authorization policy module.

All permission checks go through this module — no inline checks in endpoints.
Deny-by-default: if a function isn't listed here, it's not allowed.

Expanded in Day 5 with full RBAC + ACL logic.
"""
