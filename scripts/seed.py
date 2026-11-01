"""Database seed script — populates realistic development and demonstration records.

Usage:
    python -m scripts.seed
"""

import asyncio
import hashlib
import logging
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models.audit import AuditLog
from app.db.models.document import DocClassification, DocStatus, Document
from app.db.models.share import DocumentShare, SharePermission
from app.db.models.user import User
from app.db.models.version import DocumentVersion
from app.db.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.db.session import _get_effective_db_url
from app.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")
settings = get_settings()

SAMPLE_PDF_CONTENT = b"%PDF-1.4\n1 0 obj\n<< /Title (Seeded Document) >>\nendobj\n%%EOF"


async def seed_data() -> None:
    db_url = _get_effective_db_url()
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    storage = get_storage()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as db:
        logger.info("Connecting to database...")

        # 1. Superuser
        admin_email = "admin@securedocs.io"
        admin_stmt = select(User).where(User.email == admin_email)
        admin = (await db.scalars(admin_stmt)).first()
        if not admin:
            admin = User(
                email=admin_email,
                password_hash=hash_password("AdminSecurePassword2026!"),
                full_name="Platform Administrator",
                is_active=True,
                is_superuser=True,
            )
            db.add(admin)
            await db.flush()
            logger.info("Created superuser: %s", admin_email)

        # 2. Workspace Owners and Members
        users_info = [
            ("jane.doe@acme-aero.com", "Jane Doe", "JaneAcmePass2026!"),
            ("alice.smith@acme-aero.com", "Alice Smith", "AliceAcmePass2026!"),
            ("bob.jones@acme-aero.com", "Bob Jones", "BobAcmePass2026!"),
            ("charlie.brown@acme-aero.com", "Charlie Brown", "CharlieAcmePass2026!"),
            ("miles.dyson@cyberdyne.io", "Miles Dyson", "MilesCyberdyne2026!"),
            ("sarah.connor@resistance.org", "Sarah Connor", "SarahConnorPass2026!"),
        ]

        user_map: dict[str, User] = {}
        for email, full_name, raw_pwd in users_info:
            u_stmt = select(User).where(User.email == email)
            existing = (await db.scalars(u_stmt)).first()
            if not existing:
                existing = User(
                    email=email,
                    password_hash=hash_password(raw_pwd),
                    full_name=full_name,
                    is_active=True,
                    is_superuser=False,
                )
                db.add(existing)
                await db.flush()
                logger.info("Created user: %s", email)
            user_map[email] = existing

        # 3. Workspaces
        ws_acme_stmt = select(Workspace).where(Workspace.slug == "acme-aerospace")
        ws_acme = (await db.scalars(ws_acme_stmt)).first()
        if not ws_acme:
            ws_acme = Workspace(
                name="Acme Aerospace",
                slug="acme-aerospace",
                owner_id=user_map["jane.doe@acme-aero.com"].id,
                is_active=True,
            )
            db.add(ws_acme)
            await db.flush()
            logger.info("Created workspace: Acme Aerospace")

            # Memberships
            memberships = [
                (user_map["jane.doe@acme-aero.com"].id, WorkspaceRole.OWNER),
                (user_map["alice.smith@acme-aero.com"].id, WorkspaceRole.ADMIN),
                (user_map["bob.jones@acme-aero.com"].id, WorkspaceRole.MEMBER),
                (user_map["charlie.brown@acme-aero.com"].id, WorkspaceRole.VIEWER),
            ]
            for uid, role in memberships:
                db.add(
                    WorkspaceMember(
                        workspace_id=ws_acme.id,
                        user_id=uid,
                        role=role,
                    )
                )

            # Audit workspace creation
            db.add(
                AuditLog(
                    workspace_id=ws_acme.id,
                    actor_id=user_map["jane.doe@acme-aero.com"].id,
                    action="ws.create",
                    resource_type="workspace",
                    resource_id=ws_acme.id,
                    metadata_json={"name": ws_acme.name, "slug": ws_acme.slug},
                )
            )
            await db.flush()

        ws_cyber_stmt = select(Workspace).where(Workspace.slug == "cyberdyne-systems")
        ws_cyber = (await db.scalars(ws_cyber_stmt)).first()
        if not ws_cyber:
            ws_cyber = Workspace(
                name="Cyberdyne Systems",
                slug="cyberdyne-systems",
                owner_id=user_map["miles.dyson@cyberdyne.io"].id,
                is_active=True,
            )
            db.add(ws_cyber)
            await db.flush()
            logger.info("Created workspace: Cyberdyne Systems")

            db.add(
                WorkspaceMember(
                    workspace_id=ws_cyber.id,
                    user_id=user_map["miles.dyson@cyberdyne.io"].id,
                    role=WorkspaceRole.OWNER,
                )
            )
            await db.flush()

        # 4. Documents & Versions for Acme
        docs_to_seed = [
            (
                "Turbofan Flight Certification Dossier",
                "Restricted engineering telemetry and flight testing approval.",
                DocClassification.RESTRICTED,
                DocStatus.ACTIVE,
                "jane.doe@acme-aero.com",
                "turbofan-cert-v1.pdf",
            ),
            (
                "Q3 Titanium Alloy Supply Agreement",
                "Confidential procurement terms with titanium suppliers.",
                DocClassification.CONFIDENTIAL,
                DocStatus.ACTIVE,
                "alice.smith@acme-aero.com",
                "titanium-alloy-contract.pdf",
            ),
            (
                "Hangar Cleanroom Operational SOP",
                "Internal engineering cleanliness standard procedures.",
                DocClassification.INTERNAL,
                DocStatus.ACTIVE,
                "bob.jones@acme-aero.com",
                "cleanroom-sop.pdf",
            ),
            (
                "Open Source Aviation Telemetry Tools Disclosures",
                "Public notice regarding third-party open source licensing.",
                DocClassification.PUBLIC,
                DocStatus.ACTIVE,
                "jane.doe@acme-aero.com",
                "oss-disclosure.pdf",
            ),
        ]

        for title, desc, classification, doc_status, creator_email, filename in docs_to_seed:
            d_stmt = (
                select(Document)
                .where(Document.workspace_id == ws_acme.id)
                .where(Document.title == title)
            )
            doc = (await db.scalars(d_stmt)).first()
            if not doc:
                creator = user_map[creator_email]
                doc = Document(
                    workspace_id=ws_acme.id,
                    title=title,
                    description=desc,
                    classification=classification,
                    status=doc_status,
                    owner_id=creator.id,
                    created_by=creator.id,
                )
                db.add(doc)
                await db.flush()

                # Upload version
                storage_key = f"seed/{uuid.uuid4()}.pdf"
                checksum = hashlib.sha256(SAMPLE_PDF_CONTENT).hexdigest()

                async def _stream() -> AsyncIterator[bytes]:
                    yield SAMPLE_PDF_CONTENT

                await storage.put(storage_key, _stream())

                version = DocumentVersion(
                    document_id=doc.id,
                    version_number=1,
                    storage_key=storage_key,
                    original_filename=filename,
                    mime_type="application/pdf",
                    size_bytes=len(SAMPLE_PDF_CONTENT),
                    checksum_sha256=checksum,
                    uploaded_by=creator.id,
                )
                db.add(version)
                await db.flush()

                doc.current_version_id = version.id
                await db.flush()

                # Audit log
                db.add(
                    AuditLog(
                        workspace_id=ws_acme.id,
                        actor_id=creator.id,
                        action="doc.create",
                        resource_type="document",
                        resource_id=doc.id,
                        metadata_json={"title": title, "classification": str(classification.value)},
                    )
                )
                db.add(
                    AuditLog(
                        workspace_id=ws_acme.id,
                        actor_id=creator.id,
                        action="doc.version_create",
                        resource_type="document_version",
                        resource_id=version.id,
                        metadata_json={"version_number": 1, "size_bytes": len(SAMPLE_PDF_CONTENT)},
                    )
                )
                logger.info("Created document + version: %s", title)

                # Grant cross-tenant share on Titanium Alloy agreement to Sarah Connor
                if "Titanium" in title:
                    grantee = user_map["sarah.connor@resistance.org"]
                    share = DocumentShare(
                        document_id=doc.id,
                        user_id=grantee.id,
                        permission=SharePermission.READ,
                        granted_by=creator.id,
                        expires_at=datetime.now(UTC) + timedelta(days=30),
                    )
                    db.add(share)
                    await db.flush()
                    db.add(
                        AuditLog(
                            workspace_id=ws_acme.id,
                            actor_id=creator.id,
                            action="share.create",
                            resource_type="document_share",
                            resource_id=share.id,
                            metadata_json={
                                "target_user_id": str(grantee.id),
                                "permission": "read",
                            },
                        )
                    )
                    logger.info("Granted cross-tenant share on '%s' to %s", title, grantee.email)

        await db.commit()
        logger.info("Seeding successfully completed!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_data())
