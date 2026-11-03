# Secure Docs API — Beginner-to-Senior Interview Bible & Mental Models

> **Mentor's Note:** You don't need 10 years of experience to sound like a senior backend engineer. What separates a junior who memorized a tutorial from a senior engineer is simple: **understanding the "Why" behind every single design decision**. 
>
> When an interviewer asks you: *"Why did you use a JWT?"* or *"Why didn't you just put an if-statement in your route?"*, they are testing whether you understand trade-offs, security threats, and system boundaries. 
> 
> This guide is written from the ground up: **zero unexplained jargon**, **real-world analogies for every hard concept**, and **spoken scripts** you can practice out loud.

---

## Table of Contents
1. [Section 1: The Elevator Pitch](#section-1-the-elevator-pitch)
2. [Section 2: The Life of a Request (The Engine)](#section-2-the-life-of-a-request-the-engine)
3. [Section 3: Authentication & Security (The Bouncer)](#section-3-authentication--security-the-bouncer)
4. [Section 4: The Database & Migrations (The Vault)](#section-4-the-database--migrations-the-vault)
5. [Section 5: Secure File Handling (The Cargo Hold)](#section-5-secure-file-handling-the-cargo-hold)
6. [Section 6: The "War Stories" (How to Answer "Tell Me About a Tough Bug")](#section-6-the-war-stories)
7. [Section 7: Rapid-Fire "Stupid" Questions (That Everyone is Afraid to Ask)](#section-7-rapid-fire-stupid-questions)

---

## Section 1: The Elevator Pitch

### 1. The Recruiter Pitch (Non-Technical)
*Use this when speaking to HR, recruiters, or non-technical product managers.*

> "I built a secure, multi-tenant document vault backend—think of it as a compliance-ready Google Drive designed for enterprise organizations like aerospace or healthcare companies. 
> 
> It allows companies to store, version, and share sensitive files with strict role-based permissions and complete audit tracking. Every file upload is verified with cryptographic checksums, companies are completely isolated so they can never see each other's data, and all access is logged. I built it using Python, FastAPI, and PostgreSQL, backed by an automated test suite with over 90% code coverage."

### 2. The Hiring Manager Pitch (Technical Lead)
*Use this when a senior backend engineer or engineering manager asks: "Give me an architectural overview of your project."*

> "Secure Docs API is an asynchronous REST API built with FastAPI, SQLAlchemy 2.0 async, and PostgreSQL 16. The core architectural challenge was enforcing strict multi-tenant isolation alongside controlled cross-tenant sharing without data leakage.
> 
> Rather than scattering ad-hoc permission checks in route handlers, I decoupled authorization into a pure-function policy layer that evaluates workspace roles, document classification, and temporal share expiration with zero ORM coupling. 
> 
> For file ingestion, we stream payloads in 64KB chunks to compute SHA-256 hashes on the fly and inspect binary magic bytes using `libmagic` to prevent MIME-spoofing attacks. The database maintains an immutable, append-only version history with circular foreign keys pointing to active versions. 
> 
> Authentication uses short-lived JWTs paired with single-use refresh token rotation to automatically detect and invalidate stolen token families. Our CI pipeline runs against real PostgreSQL containers and includes automated migration rollbacks and route-reflection meta-tests."

---

## Section 2: The Life of a Request (The Engine)

### The Jargon Buster: 3 Fundamental Concepts

#### 1. "Middleware"
* **Analogy:** The security checkpoint and metal detector at an airport.
* **What is it?** A piece of code that wraps around your entire application. Every single incoming request must pass through it *before* reaching your endpoints, and every outgoing response passes back through it *before* leaving the server.
* **Why did we use it?** If you have 50 endpoints and want to add security headers or track request IDs, you don't want to copy-paste that code 50 times. Middleware handles cross-cutting concerns in one central spot.
* **Where is it?** `app/main.py` (`request_middleware`).

#### 2. "Dependency Injection" (DI)
* **Analogy:** Ordering a rental car delivered to your hotel driveway instead of having to build the engine, forge the steel, and pump the gas yourself before every trip.
* **What is it?** A programming technique where a function *asks* for the tools it needs (like a database connection or the currently logged-in user) instead of creating them from scratch inside the function body.
* **Why did we use it?** It makes code modular and testable. In our test suite, we can easily swap the real database for a test database without changing a single line of endpoint code.
* **Where is it?** `app/api/deps.py` (`get_db`, `get_current_user`).

#### 3. "Async / Await"
* **Analogy:** A waiter at a restaurant. A synchronous waiter takes table 1's order, walks to the kitchen, and stands there staring at the chef for 20 minutes until the steak is cooked, completely ignoring tables 2, 3, and 4. An **async waiter** gives the order to the chef, immediately walks over to take orders from tables 2, 3, and 4, and only comes back to table 1 when the kitchen bell rings.
* **What is it?** Non-blocking input/output (I/O). While Python waits for PostgreSQL to finish a slow database query or waits for a file to write to disk, the server pauses that task (`await`) and handles requests from other users on the same CPU thread.
* **Why did we use it?** High throughput. A synchronous Python server might freeze after 20 simultaneous database queries; an async server handles thousands of concurrent connections effortlessly.
* **Where is it?** Everywhere in `app/api/`, `app/services/`, and `app/db/session.py`.

---

### Step-by-Step: From Swagger "Execute" to Database and Back

Here is the exact journey of a request when a user clicks **"Execute"** on `POST /api/v1/workspaces/{id}/documents`:

```
[ User Browser / Swagger UI ]
              │  HTTP POST (JSON payload + Bearer Token)
              ▼
┌────────────────────────────────────────────────────────┐
│ 1. Middleware Layer (app/main.py)                      │
│    - Assigns unique X-Request-ID (e.g., 'a8f1-...')    │
│    - Checks Content-Length guard (<10MB)               │
└─────────────┬──────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────┐
│ 2. Routing & Rate Limiting (SlowAPI)                   │
│    - Checks if caller exceeded 10 req/minute           │
└─────────────┬──────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────┐
│ 3. Dependency Injection Pipeline (app/api/deps.py)     │
│    - Reads 'Authorization: Bearer <JWT>' header        │
│    - Decodes JWT, validates signature and expiration   │
│    - Loads User model from DB (ensures account active) │
│    - Opens clean AsyncSession database transaction     │
└─────────────┬──────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────┐
│ 4. Pydantic v2 Schema Validation                       │
│    - Parses incoming JSON into DocumentCreate schema   │
│    - Validates strings, enums, required fields         │
│    - If invalid, returns RFC 7807 422 Error envelope   │
└─────────────┬──────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────┐
│ 5. Service Layer & Pure Policy Check                   │
│    - Queries workspace membership for the user         │
│    - Calls can_create_document(user_role) in policy    │
│    - If False -> raises AppError(403, 'FORBIDDEN')     │
└─────────────┬──────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────┐
│ 6. Database Transaction (SQLAlchemy + asyncpg)         │
│    - Inserts new Document row into PostgreSQL          │
│    - Inserts AuditLog row in the SAME transaction      │
│    - session.commit() writes changes atomically        │
└─────────────┬──────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────┐
│ 7. Outgoing Middleware & Response Formatting           │
│    - Pydantic serializes ORM model to JSON response    │
│    - Middleware injects security headers (CSP, HSTS)   │
│    - Attaches X-Request-ID to response headers         │
│    - Sends HTTP 201 Created back to client             │
└────────────────────────────────────────────────────────┘
```

#### How to Say This in an Interview:
> *"When a request hits our API, it first passes through our custom HTTP middleware, which assigns an `X-Request-ID` for end-to-end distributed tracing and validates that the payload doesn't exceed our size ceilings.* 
> 
> *Next, FastAPI's dependency injection container kicks in: it verifies rate limits via SlowAPI, decodes the JWT access token to authenticate the user, and opens an isolated database session. Pydantic validates the request types, our service layer verifies permissions using our pure policy module, and SQLAlchemy writes both the business entity and an audit log inside a single atomic transaction. Finally, the response is serialized and returned with strict security headers."*

---

## Section 3: Authentication & Security (The Bouncer)

### 1. JSON Web Tokens (JWT) vs. Session Cookies
* **Analogy:** 
  * **Session Cookie:** Checking your coat at a fancy club. The club gives you a claim ticket with a number (`142`). The club must maintain a huge physical coat closet (a central database) to look up ticket `142` every single time you want your coat. If the coat closet burns down or the server restarts, nobody gets their coat.
  * **JWT (JSON Web Token):** A tamper-proof boarding pass with your name, seat number, and flight time stamped directly on it, signed with the airline captain's secret digital signature. The flight attendant doesn't need to call central dispatch to verify who you are; they just look at the cryptographic stamp.
* **What is it?** A digitally signed string containing JSON data (`sub: user_id`, `exp: expiration_timestamp`).
* **Why did we use it?** It is **stateless**. The API server can verify a user's identity across hundreds of servers without querying the database on every micro-request.
* **Where is it?** `app/core/security.py` (`create_access_token`, `decode_token`).

---

### 2. Refresh Token Rotation & Token Families (The Hardest Concept Made Simple)

```
[ Normal Flow: Fresh Token Issued ]
Login ──> Receives Refresh Token A (Family 1)
Refresh with A ──> Token A marked REVOKED
               ──> Receives NEW Refresh Token B (Family 1)

[ Attack Flow: Intercepted Token Replayed ]
Thief steals Token A and tries to use it LATER
Server looks up Token A in DB ──> "Wait! Token A is ALREADY REVOKED!"
Server Conclusion ──> "A breach occurred! Token reuse detected!"
Action ──> Server IMMEDIATELY REVOKES ALL TOKENS IN FAMILY 1!
Result ──> Both the legitimate user and the thief are logged out.
           The attacker is locked out instantly.
```

* **Analogy:** 
  Imagine a bank gives you a temporary security wristband (Token A). When Token A expires, you hand it back to the teller. The teller shreds Token A and hands you a brand-new wristband (Token B), writing down in their ledger that Token A is shredded.
  
  Now, imagine a pickpocket had cloned your old Token A and walks up to the teller 10 minutes later presenting Token A.
  
  The teller checks the ledger and sees: *"Token A was already shredded! Someone is trying to impersonate this customer!"*
  
  The teller doesn't just reject Token A; the teller presses the emergency alarm and cancels **every single wristband tied to your account family** (Token B included). The legitimate customer will have to re-enter their password, but the thief is completely locked out.

* **What is it?** 
  * Access Tokens live for only **15 minutes**.
  * Refresh Tokens live for **7 days**.
  * When a refresh token is used, it is **rotated** (marked revoked, and a brand-new one is issued).
  * All tokens born from the same initial login share a `family_id`.
* **Why did we use it?** If an access token is stolen, the damage is capped at 15 minutes. If a refresh token is stolen, our reuse detection catches the replay and immediately revokes all access.
* **Where is it?** `app/services/auth_service.py` (`refresh_access_token`) and `app/db/models/user.py` (`RefreshToken`).

---

### 3. The "404 vs 403 Rule" (Cross-Tenant Concealment)

* **Analogy:**
  Imagine an apartment building with private floors. 
  * If a stranger walks up to Penthouse B and jiggles the handle, and a guard says: *"You don't have permission to enter Penthouse B"* (**403 Forbidden**), the guard has just confirmed to the stranger: *"Yes, Penthouse B exists, and someone valuable lives here."*
  * Instead, our guard acts as if Penthouse B does not exist at all: *"There is no Penthouse B on this directory"* (**404 Not Found**).
* **What is it?**
  * **403 Forbidden:** "I know what you're asking for, but you aren't allowed to touch it."
  * **404 Not Found:** "I have no idea what you're talking about."
* **Why is this critical for security?**
  In a multi-tenant B2B app, **existence is sensitive data**. If Company A guesses a random UUID belonging to Company B, returning a 403 tells Company A: *"Bingo! That document exists!"* 
  By returning a **404**, an attacker cannot determine whether a document exists, protecting our customers from ID enumeration and reconnaissance attacks.
* **Where is it?** `app/services/document_service.py` (`get_document`).

---

### 4. Pure-Function Policy Layer (`app/core/policies/access.py`)

* **Analogy:** A pocket calculator. If you type `2 + 2`, it returns `4`. It doesn't care who is holding the calculator, it doesn't call an API, and it doesn't touch the internet. It is a **pure function**: given the exact same inputs, it always returns the exact same output with zero side effects.
* **What did we do?**
  Instead of writing:
  ```python
  # BAD JUNIOR PATTERN: Mixed into route handlers
  if user.role != "admin" or doc.classification == "restricted":
      raise HTTPException(403)
  ```
  We extracted every single permission check into pure functions:
  ```python
  # SENIOR PATTERN: Pure, testable, decoupled
  def can_view_document(
      actor_role: WorkspaceRole | None,
      doc: DocumentAccessProtocol,
      has_active_share: bool = False,
  ) -> bool:
      if has_active_share:
          return True
      if actor_role is None:
          return False
      if doc.classification == DocClassification.RESTRICTED:
          return actor_role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
      return True
  ```
* **Why did we do this?**
  1. **Speed & Reliability:** We test all 33 role, status, and classification combinations in **0.02 seconds** because the test doesn't need to boot a database or make HTTP calls.
  2. **Zero Framework Coupling:** If we migrate from FastAPI to another framework tomorrow, our business security logic remains 100% unchanged.
* **Where is it?** `app/core/policies/access.py` and `tests/unit/test_access_policy.py`.

#### How to Say This in an Interview:
> *"For authorization, we implemented a pure-function policy layer that evaluates user permissions using structural typing interfaces. This completely decouples security rules from both the database ORM and FastAPI route handlers. It allowed us to achieve 100% test coverage across our permission matrix in milliseconds.* 
> 
> *Additionally, we enforce the '404 vs 403 rule' to prevent cross-tenant metadata leakage: if a user requests a resource outside their authorized workspace, we return 404 Not Found rather than 403 Forbidden so attackers cannot enumerate valid document IDs."*

---

## Section 4: The Database & Migrations (The Vault)

### 1. SQLAlchemy 2.0 & ORM vs. Raw SQL
* **Analogy:** A universal translator. Instead of writing raw SQL strings (`SELECT * FROM users WHERE id = '...'`) which might differ between PostgreSQL and SQLite and are vulnerable to syntax errors, an ORM (Object-Relational Mapper) lets us write type-safe Python code (`select(User).where(User.id == user_id)`) that compiles into optimized SQL for whichever database is running.
* **Why did we use it?**
  * Automatic protection against **SQL Injection** attacks (parameterized queries).
  * Strict typing with Python 3.11+ type hints (`Mapped[str]`).
  * Seamless support for async operations via `asyncpg`.
* **Where is it?** `app/db/models/` and `app/db/session.py`.

---

### 2. Database Migrations (Alembic) vs. `Base.metadata.create_all()`
* **Analogy:** 
  * `create_all()` is like building a house from a sketch on day one. But what happens 6 months later when you want to add a second bathroom? `create_all()` doesn't know how to remodel; it can only build on an empty lot.
  * **Alembic Migrations** are Git for your database. Each migration file is a revision (`0001_users`, `0002_tokens`) with an `upgrade()` function and a `downgrade()` function. It knows how to alter existing production tables without losing data.
* **Why did we use it?**
  In CI and production, `create_all()` cannot create custom PostgreSQL extensions (`citext`, `pg_trgm`) and cannot handle circular table dependencies. Alembic tracks schema history deterministically.
* **Where is it?** `alembic/versions/` and `alembic/env.py`.

---

### 3. The Circular Foreign Key (`current_version_id`)
* **The Problem (The Chicken-and-Egg Riddle):**
  * A `Document` needs to point to its active `DocumentVersion` (`current_version_id`).
  * A `DocumentVersion` needs to point back to the parent `Document` (`document_id`).
  * If both tables enforce foreign keys on creation, **neither table can be created first** because each depends on the other!
* **The Solution:**
  1. In Migration `0004`, we create `documents` with a plain UUID column for `current_version_id` (no foreign key constraint yet).
  2. In Migration `0005`, we create `document_versions` with a foreign key pointing to `documents.id`.
  3. Finally, in Migration `0005`, we use `op.create_foreign_key(..., use_alter=True, ondelete="SET NULL")` to add the circular constraint to `documents` via an `ALTER TABLE` statement.
* **Why do we have this column at all?**
  Speed. Without `current_version_id`, finding the current version of 100 documents requires an expensive `GROUP BY` subquery to calculate `MAX(version_number)`. With this pointer, it is an instant `O(1)` index lookup.
* **Where is it?** `alembic/versions/0005_create_versions.py`.

#### How to Say This in an Interview:
> *"We separate `documents` and `document_versions` to maintain an immutable, append-only history. To avoid expensive `GROUP BY MAX()` subqueries when querying document lists, the `documents` table stores a `current_version_id` pointer.* 
> 
> *Because this creates a circular foreign key relationship, we resolved it in Alembic using a deferred `ALTER TABLE` migration with `ondelete='SET NULL'`. This ensures fast reads while allowing safe cascade deletes."*

---

## Section 5: Secure File Handling (The Cargo Hold)

### 1. "Magic Bytes" vs. File Extensions
* **Analogy:** A criminal putting a doctor's lab coat over their prison jumpsuit. A naive bouncer looks at the coat and says: *"Come on in, doctor!"* (trusting the `.pdf` extension). A smart bouncer asks for their medical license and runs their fingerprints (checking the **Magic Bytes**).
* **What is it?** Every file type starts with specific hexadecimal bytes at the very beginning of the binary stream. For example, all PDF files start with `%PDF-` (`0x25 0x50 0x44 0x46`).
* **Why did we use it?** An attacker can rename a malicious executable `virus.exe` to `invoice.pdf` and send `Content-Type: application/pdf`. Our backend reads the first 2,048 bytes and uses `python-magic` (`libmagic`) to inspect the real binary signature, rejecting spoofed files immediately with `415 Unsupported Media Type`.
* **Where is it?** `app/services/document_service.py` (`_detect_mime_type`).

---

### 2. Path Traversal & UUID Storage Keys
* **Analogy:** A coat-check counter. When you check your jacket, the attendant doesn't write *"Bob's black jacket"* and leave it on the counter; they hand you ticket number `#8472` and hang your jacket in slot `8472`.
* **What is Path Traversal?**
  If a user uploads a file named `../../../../etc/passwd` and the server writes that directly to disk, the `../` dots walk up the directory tree and overwrite sensitive operating system files.
* **How did we solve it?**
  We **never** use the user's filename on disk. When a file is uploaded, we generate an unguessable UUID (e.g., `f47ac10b-58cc-4372-a567-0e02b2c3d479`). 
  The file is saved on disk under that UUID. The user's original human-readable filename is saved safely inside the PostgreSQL database and restored during download via HTTP headers:
  ```http
  Content-Disposition: attachment; filename="report.pdf"; filename*=UTF-8''Report.pdf
  ```
* **Where is it?** `app/storage/local.py` and `app/services/download_service.py`.

---

### 3. Streaming File Ingestion & On-the-Fly SHA-256
* **Analogy:** Inspecting cargo on a moving conveyor belt instead of unloading an entire cargo ship into a warehouse just to weigh it.
* **What is it?** We read the incoming file in **64KB chunks**. As each chunk arrives from the network:
  1. We write that chunk to disk.
  2. We pass that chunk to `hashlib.sha256().update(chunk)`.
* **Why did we do this?** Memory safety. If 20 users upload 50MB files simultaneously, a naive backend that calls `await file.read()` buffers 1,000MB (1GB) of data directly into server RAM, crashing the server with an Out-of-Memory (OOM) error. Our streaming approach uses less than 1MB of RAM regardless of file size.
* **Where is it?** `app/services/document_service.py` (`create_version`).

#### How to Say This in an Interview:
> *"For file ingestion, we implement defense-in-depth: we reject client-reported MIME types and instead inspect the initial 2,048 bytes via `libmagic` to verify true binary magic bytes. Files are streamed in 64KB chunks to keep memory footprint minimal while calculating a SHA-256 checksum on the fly.* 
> 
> *To eliminate path traversal and filesystem collision vulnerabilities, files are stored on disk under opaque UUID keys, while original filenames are preserved in PostgreSQL metadata and returned during download via RFC 6266 headers."*

---

## Section 6: The "War Stories"

*Interviewers love to ask: "Tell me about a difficult bug you encountered and how you resolved it." Here are two real, authentic engineering stories from our build log.*

### War Story 1: The CITEXT Collation & Dialect Masking Bug

```
[ Problem Statement ]
"I wanted to guarantee case-insensitive email uniqueness so 'Admin@Corp.com' and 'admin@corp.com' 
could not register duplicate accounts."

[ What Broke ]
PostgreSQL uses the native `CITEXT` extension for this. But during local testing on SQLite, 
our test suite was green even though SQLite was secretly allowing duplicate accounts!

[ The Investigation ]
I looked at our SQLite test compiler shim in `conftest.py`. It had mapped `CITEXT` to plain `TEXT`. 
In SQLite, a `TEXT` column uses binary collation (`BINARY`) by default, meaning SQLite considered 
uppercase and lowercase letters different. The test wasn't testing what production would actually do!

[ The Fix ]
I updated the SQLAlchemy compiler shim to compile `CITEXT` as `TEXT COLLATE NOCASE` on SQLite. 
Suddenly, SQLite enforced case-insensitivity identically to PostgreSQL, and we added an explicit 
regression test to prevent future dialect drift.
```

* **How to say it in the interview:**
  > *"We used PostgreSQL's `CITEXT` type for case-insensitive email uniqueness. To keep local unit tests fast without mandating a running Docker daemon, we shimmed `CITEXT` to SQLite `TEXT`. 
  > 
  > However, I realized SQLite's default collation is case-sensitive, which masked potential uniqueness bugs in local test runs. I updated our dialect compiler to map `CITEXT` to `TEXT COLLATE NOCASE`, aligning SQLite's behavior with PostgreSQL and ensuring tests validate real production semantics."*

---

### War Story 2: The Blank Swagger UI & Content Security Policy Bug

```
[ Problem Statement ]
"We booted our application server and visited `/docs` to test endpoints, 
but the browser rendered a completely blank white screen."

[ What Broke ]
FastAPI generated the OpenAPI HTML, but Swagger UI refused to render any interactive UI components.

[ The Investigation ]
I opened the browser developer console and saw several red errors: 
`Refused to load script from cdn.jsdelivr.net because it violates Content-Security-Policy: default-src 'none'`.
Our custom security headers middleware in `app/main.py` was unconditionally attaching an aggressive 
Content-Security-Policy (`default-src 'none'`) to EVERY response, completely blocking Swagger's CDN 
scripts, stylesheets, and inline JavaScript initialization.

[ The Fix ]
I modified the middleware to check `request.url.path`. If the request is for `/docs`, `/redoc`, 
or `/openapi.json`, it serves a relaxed CSP allowing scripts and styles from the trusted CDN 
and inline scripts. All other API endpoints continue to receive the strict `default-src 'none'` header.
```

* **How to say it in the interview:**
  > *"When we enabled our global security middleware, our Swagger UI documentation at `/docs` rendered a blank white page. Inspecting the browser console revealed that our Content Security Policy header was set to `default-src 'none'`, which blocked Swagger's CDN assets and inline scripts. 
  > 
  > I resolved this by updating the middleware to apply route-specific security policies: documentation endpoints permit trusted CDN assets, while all public API data routes maintain strict `default-src 'none'` headers to prevent cross-site scripting."*

---

## Section 7: Rapid-Fire "Stupid" Questions

### 1. "Why did you use UUIDs instead of standard auto-incrementing numbers (1, 2, 3) for IDs?"
> *"Two reasons: Security and distribution. Auto-incrementing IDs are vulnerable to enumeration attacks—an attacker can simply guess `/documents/1`, `/documents/2`, and scrape your database or deduce how many customers you have. UUIDv4 is 128-bit and unguessable. Additionally, UUIDs can be generated on client or worker nodes without needing a centralized database coordinate lock."*

### 2. "What happens if the server crashes right in the middle of a file upload?"
> *"Our database operations and file saves are decoupled. If the network drops or the server dies mid-upload, the database transaction is automatically rolled back by SQLAlchemy's `AsyncSession`, meaning no partial document or version row is ever committed. A background janitor task can safely sweep temporary storage directories to clean up unreferenced orphaned files."*

### 3. "How would you handle 10,000 users uploading files at the exact same second?"
> *"Right now, files stream through our API server. At 10,000 concurrent uploads, streaming through web workers consumes available network sockets. In a high-scale v2, we would implement **Direct-to-S3 Presigned Uploads**: the client asks the API for a temporary presigned upload URL, uploads the file directly to AWS S3, and S3 notifies our API via a webhook or SQS queue upon completion, taking all upload bandwidth off our servers."*

### 4. "Why did you use Argon2id instead of bcrypt or SHA-256 for passwords?"
> *"SHA-256 is a general-purpose cryptographic hash, not a password hash; modern GPUs can compute billions of SHA-256 hashes per second, making brute-force trivial. Bcrypt is older and only CPU-bound. Argon2id is the modern OWASP standard and winner of the Password Hashing Competition: it is **memory-hard**, meaning it requires significant RAM to compute, rendering GPU and ASIC hardware brute-force attacks economically impossible."*

### 5. "What happens if two people in the same company upload a file with the same name at the same time?"
> *"Nothing breaks. Because our physical storage files are saved under unique UUIDs (`storage/workspaces/{ws_id}/{uuid}`), there is no filesystem collision. At the database level, documents can share titles or exist across different workspaces independently without triggering constraint violations."*
