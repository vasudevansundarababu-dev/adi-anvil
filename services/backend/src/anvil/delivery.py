"""Network-free mail simulation. No real sender, SMTP, email SDK or external address."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from anvil import artifacts, auth, domain
from anvil.db import audit, digest, one, uid
from anvil.evaluation import enqueue
from anvil.reports import validity
from anvil.schemas import Strict


class Contact(Strict):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(pattern=r"^[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9.-]{1,100}\.invalid$")
    organization_label: str = Field(min_length=2, max_length=100)
    contact_basis: str = Field(min_length=10, max_length=2000)


class ContactDecision(Strict):
    status: Literal["approved", "suppressed"]


class Sender(Strict):
    name: str = Field(min_length=3, max_length=100)
    scenario: Literal["accepted", "failed", "unknown"]


class Approval(Strict):
    recipient_contact_id: UUID
    sender_connection_id: UUID
    expires_in_minutes: int = Field(default=60, ge=1, le=480)


class Send(Strict):
    delivery_approval_id: UUID
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def release_owner(c, user, roles):
    auth.require(roles, "product-owner")
    if not one(
        c,
        "SELECT 1 FROM anvil.project_assignments WHERE user_id=%s AND capability='release_owner' AND active",
        (user,),
    ):
        raise HTTPException(403, "Designated release owner required")


def binding(c, kit_id, contact_id, sender_id):
    kit = domain.get_resource(c, kit_id)
    if kit["kind"] != "sales_kit" or kit["lifecycle"] != "approved":
        raise HTTPException(409, "Current approved kit required")
    report_revision = domain.get_revision(
        c, kit["content"]["report_revision_id"], "report", ["approved"]
    )
    report = domain.get_resource(c, report_revision["resource_id"])
    validity(c, report)
    contact = one(c, "SELECT * FROM anvil.sales_contacts WHERE id=%s", (contact_id,))
    sender = one(c, "SELECT * FROM anvil.fixture_senders WHERE id=%s", (sender_id,))
    if not contact or not sender:
        raise HTTPException(404, "Contact or fixture sender not found")
    if contact["status"] != "approved" or sender["status"] != "active":
        raise HTTPException(409, "Approved unsuppressed contact and active fixture sender required")
    for person, role in [
        (contact["approved_by"], "product-owner"),
        (sender["created_by"], "admin"),
        (sender["activated_by"], "admin"),
    ]:
        if not one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.role=%s AND m.active AND u.active",
            (kit["project_id"], person, role),
        ):
            raise HTTPException(409, "Contact or sender authority no longer active")
    if not contact["email"].endswith(".invalid"):
        raise HTTPException(409, "Only reserved .invalid fixture recipients are supported")
    attachment = artifacts.read(c, kit["content"]["artifacts"]["sales-kit.pdf"])
    email = artifacts.read(c, kit["content"]["artifacts"]["email-draft.txt"])
    if len(attachment) > 5 * 1024 * 1024 or b"localhost" in email or b"127.0.0.1" in email:
        raise HTTPException(409, "Attachment size or evidence-link gate failed")
    import hashlib

    h = digest(
        {
            "kit_revision": str(kit["current_revision_id"]),
            "kit_hash": kit["content_hash"],
            "contact_id": str(contact["id"]),
            "contact_hash": contact["content_hash"],
            "contact_version": contact["row_version"],
            "sender_id": str(sender["id"]),
            "sender_hash": sender["content_hash"],
            "sender_version": sender["row_version"],
            "pdf_hash": hashlib.sha256(attachment).hexdigest(),
            "email_hash": hashlib.sha256(email).hexdigest(),
            "permitted_use": "local_network_free_fixture_only",
        }
    )
    return kit, contact, sender, h


def dispatch_fixture(c, job):
    delivery = one(
        c, "SELECT * FROM anvil.sales_deliveries WHERE id=%s FOR UPDATE", (job["target_id"],)
    )
    if not delivery or delivery["status"] != "queued":
        return
    approval = one(
        c, "SELECT * FROM anvil.delivery_approvals WHERE id=%s", (delivery["approval_id"],)
    )
    try:
        if not approval or approval["expires_at"] <= datetime.now(timezone.utc):
            raise HTTPException(409, "Approval expired")
        if not one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.role='sales' AND m.active AND u.active",
            (job["project_id"], delivery["requested_by"]),
        ):
            raise HTTPException(403, "Requesting Sales identity no longer active")
        if not one(
            c,
            "SELECT 1 FROM anvil.project_assignments a JOIN anvil.users u ON u.id=a.user_id JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.user_id WHERE a.user_id=%s AND a.capability='release_owner' AND a.active AND u.active AND m.role='product-owner' AND m.active",
            (approval["approved_by"],),
        ):
            raise HTTPException(403, "Release approval authority no longer active")
        revision = domain.get_revision(c, approval["kit_revision_id"], "sales_kit", ["approved"])
        kit, contact, sender, h = binding(
            c, revision["resource_id"], approval["contact_id"], approval["sender_id"]
        )
        if h != approval["binding_hash"] or h != delivery["binding_hash"]:
            raise HTTPException(409, "Delivery binding changed")
    except HTTPException:
        c.execute(
            "UPDATE anvil.sales_deliveries SET status='blocked',error_code='current_authority_or_evidence_blocked' WHERE id=%s",
            (delivery["id"],),
        )
        audit(c, job["project_id"], None, "fixture_delivery.blocked", delivery["id"])
        return
    # Simulation only: no network operation exists. Unknown acceptance is a terminal state.
    status = "fixture_" + sender["scenario"]
    c.execute(
        "UPDATE anvil.sales_deliveries SET status=%s,attempts=attempts+1,accepted_at=CASE WHEN %s='fixture_accepted' THEN now() ELSE NULL END WHERE id=%s",
        (status, status, delivery["id"]),
    )
    audit(
        c,
        job["project_id"],
        None,
        "fixture_delivery." + sender["scenario"],
        delivery["id"],
        {"network_requests": 0},
    )


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}")

    @router.get("/sales-contacts")
    def contacts(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "sales", "product-owner")
            return wrap(
                c.execute(
                    "SELECT id,name,email,organization_label,status,row_version FROM anvil.sales_contacts ORDER BY name LIMIT 100"
                ).fetchall(),
                request,
            )

    @router.post("/sales-contacts")
    def create_contact(project: UUID, body: Contact, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "sales")

            def act():
                cid = uid()
                c.execute(
                    "INSERT INTO anvil.sales_contacts(id,project_id,name,email,organization_label,contact_basis,created_by,content_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        cid,
                        project,
                        body.name,
                        body.email,
                        body.organization_label,
                        body.contact_basis,
                        user,
                        digest(body.model_dump()),
                    ),
                )
                audit(c, project, user, "fixture_contact.created", cid)
                return {"id": cid, "row_version": 1, "status": "draft"}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/sales-contacts/{cid}/decision")
    def decide_contact(project: UUID, cid: UUID, body: ContactDecision, request: Request):
        with context(request, project) as (c, user, roles):
            release_owner(c, user, roles)

            def act():
                contact = one(
                    c, "SELECT * FROM anvil.sales_contacts WHERE id=%s FOR UPDATE", (cid,)
                )
                if not contact:
                    raise HTTPException(404, "Contact not found")
                domain.etag(contact, request.headers.get("if-match"))
                if contact["created_by"] == user:
                    raise HTTPException(409, "Independent contact review required")
                c.execute(
                    "UPDATE anvil.sales_contacts SET status=%s,approved_by=%s,row_version=row_version+1 WHERE id=%s",
                    (body.status, user, cid),
                )
                audit(c, project, user, "fixture_contact." + body.status, cid)
                return {
                    "id": str(cid),
                    "status": body.status,
                    "row_version": contact["row_version"] + 1,
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.get("/fixture-senders")
    def senders(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "sales", "product-owner")
            return wrap(
                c.execute(
                    "SELECT id,name,status,scenario,row_version FROM anvil.fixture_senders ORDER BY name LIMIT 100"
                ).fetchall(),
                request,
            )

    @router.post("/fixture-senders")
    def create_sender(project: UUID, body: Sender, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                sid = uid()
                c.execute(
                    "INSERT INTO anvil.fixture_senders(id,project_id,name,scenario,created_by,content_hash) VALUES(%s,%s,%s,%s,%s,%s)",
                    (sid, project, body.name, body.scenario, user, digest(body.model_dump())),
                )
                audit(c, project, user, "fixture_sender.created", sid)
                return {"id": sid, "status": "draft", "row_version": 1}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/fixture-senders/{sid}/activate")
    def activate(project: UUID, sid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")

            def act():
                sender = one(
                    c, "SELECT * FROM anvil.fixture_senders WHERE id=%s FOR UPDATE", (sid,)
                )
                if not sender:
                    raise HTTPException(404, "Fixture sender not found")
                domain.etag(sender, request.headers.get("if-match"))
                if sender["created_by"] == user:
                    raise HTTPException(409, "Distinct Admin required")
                c.execute(
                    "UPDATE anvil.fixture_senders SET status='active',activated_by=%s,row_version=row_version+1 WHERE id=%s",
                    (user, sid),
                )
                audit(c, project, user, "fixture_sender.activated", sid)
                return {
                    "id": str(sid),
                    "status": "active",
                    "row_version": sender["row_version"] + 1,
                }

            return wrap(idempotent(c, project, user, request, {}, act), request)

    @router.post("/sales-kits/{kid}/delivery-approvals")
    def approve(project: UUID, kid: UUID, body: Approval, request: Request):
        with context(request, project) as (c, user, roles):
            release_owner(c, user, roles)

            def act():
                kit, contact, sender, h = binding(
                    c, kid, body.recipient_contact_id, body.sender_connection_id
                )
                if kit["created_by"] == user:
                    raise HTTPException(409, "Independent kit release owner required")
                aid = uid()
                c.execute(
                    "INSERT INTO anvil.delivery_approvals(id,project_id,kit_revision_id,contact_id,sender_id,binding_hash,approved_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        aid,
                        project,
                        kit["current_revision_id"],
                        contact["id"],
                        sender["id"],
                        h,
                        user,
                        datetime.now(timezone.utc) + timedelta(minutes=body.expires_in_minutes),
                    ),
                )
                audit(c, project, user, "fixture_delivery.approved", aid)
                return {"id": aid, "content_hash": h, "mode": "network_free_fixture"}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/sales-kits/{kid}/simulate-send")
    def simulate(project: UUID, kid: UUID, body: Send, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "sales")

            def act():
                a = one(
                    c,
                    "SELECT * FROM anvil.delivery_approvals WHERE id=%s",
                    (body.delivery_approval_id,),
                )
                if not a:
                    raise HTTPException(404, "Approval not found")
                kit, contact, sender, h = binding(c, kid, a["contact_id"], a["sender_id"])
                if (
                    a["expires_at"] <= datetime.now(timezone.utc)
                    or a["kit_revision_id"] != kit["current_revision_id"]
                    or h != a["binding_hash"]
                    or h != body.content_hash
                ):
                    raise HTTPException(409, "Expired or mismatched delivery approval")
                old = one(
                    c, "SELECT id,status FROM anvil.sales_deliveries WHERE binding_hash=%s", (h,)
                )
                if old:
                    return old
                did = uid()
                c.execute(
                    "INSERT INTO anvil.sales_deliveries(id,project_id,approval_id,requested_by,binding_hash) VALUES(%s,%s,%s,%s,%s)",
                    (did, project, a["id"], user, h),
                )
                enqueue(c, project, "fixture_mail", did, "fixture-mail:" + str(a["id"]))
                audit(c, project, user, "fixture_delivery.queued", did)
                return {"id": did, "status": "queued", "network_requests": 0}

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.get("/sales-deliveries/{did}")
    def delivery(project: UUID, did: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "sales", "product-owner")
            row = one(
                c,
                "SELECT id,status,attempts,error_code,accepted_at FROM anvil.sales_deliveries WHERE id=%s",
                (did,),
            )
            if not row:
                raise HTTPException(404, "Delivery not found")
            return wrap(
                {
                    **row,
                    "mode": "network_free_fixture",
                    "real_email_sent": False,
                    "inbox_delivery": "not_applicable",
                },
                request,
            )

    @router.get("/delivery-approvals")
    def approvals(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "sales", "product-owner")
            return wrap(
                c.execute(
                    "SELECT id,kit_revision_id,contact_id,sender_id,binding_hash,expires_at FROM anvil.delivery_approvals ORDER BY created_at DESC LIMIT 100"
                ).fetchall(),
                request,
            )

    @router.get("/sales-deliveries")
    def deliveries(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "sales", "product-owner")
            return wrap(
                c.execute(
                    "SELECT id,status,attempts,error_code,accepted_at FROM anvil.sales_deliveries ORDER BY created_at DESC LIMIT 100"
                ).fetchall(),
                request,
            )

    return router
