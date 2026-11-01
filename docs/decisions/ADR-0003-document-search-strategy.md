# ADR-0003: Document Search Strategy — GIN pg_trgm vs ILIKE

## Status
Accepted

## Context
Documents require substring search across `title` and `description` within a workspace tenant. Typical queries include partial words, project codenames, vendor names, and internal reference codes (e.g., "SOC2", "MSA-2024"). The workspace search endpoint must support filtering by query string (`q`), status, classification, and date bounds while enforcing strict multi-tenant isolation.

Two primary indexing strategies exist in PostgreSQL for substring search:
1. Standard B-Tree with `ILIKE '%term%'`: Requires full sequential scan of all documents in the workspace because leading wildcards cannot utilize standard B-Tree indexes.
2. PostgreSQL `pg_trgm` extension with GIN (Generalized Inverted Index) trigram index: Breaks strings into 3-character sequences and indexes them, enabling indexed lookups for `LIKE`/`ILIKE` with arbitrary wildcards.

Full-text search (tsvector/tsquery) was considered but explicitly scoped out because records management searches frequently match exact code fragments, partial acronyms, and alphanumeric identifiers that linguistic stemmers inappropriately tokenize or discard.

## Decision
We adopt `pg_trgm` with a GIN index on `title` in PostgreSQL for production, combined with standard SQL `ILIKE` filtering in query generation:
1. Migration `0004_documents` enables the `pg_trgm` extension and creates a GIN index:
   `CREATE INDEX ix_documents_title_trgm ON documents USING gin (title gin_trgm_ops);`
2. Search queries generate `OR` filters across `title.ilike(f"%{q}%")` and `description.ilike(f"%{q}%")`.
3. In tests running on in-memory SQLite, standard case-insensitive `LIKE` functions transparently without PostgreSQL extension dependencies.
4. Composite partial index `ix_documents_workspace_created` on `(workspace_id, created_at DESC) WHERE deleted_at IS NULL` guarantees fast pagination and sort order retrieval for tenant document listings.

## Consequences
- Fast substring search in PostgreSQL without full table scans even with millions of documents per workspace.
- GIN index writes have slight overhead during document creation and title updates, which is acceptable because document writes are low-frequency compared to reads and searches.
- Test suite compatibility is preserved across both PostgreSQL and SQLite runners.
