"""Webhook CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from paic.api.schemas.webhook import WebhookCreate, WebhookResponse, WebhookUpdate
from paic.core.crypto import seal
from paic.db.models import Webhook
from paic.db.session import get_session

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _to_response(webhook: Webhook) -> WebhookResponse:
    return WebhookResponse.model_validate(webhook)


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(
    body: WebhookCreate,
    db: Session = Depends(get_session),  # noqa: B008
) -> WebhookResponse:
    """Create a new webhook for a tenant, storing the secret encrypted at rest."""
    ciphertext, nonce = seal(body.secret)
    webhook = Webhook(
        tenant_id=body.tenant_id,
        url=body.url,
        secret_ciphertext=ciphertext,
        secret_nonce=nonce,
        active=body.active,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    return _to_response(webhook)


@router.get("", response_model=list[WebhookResponse])
def list_webhooks(
    tenant_id: str = Query(..., description="Filter webhooks by tenant ID"),
    db: Session = Depends(get_session),  # noqa: B008
) -> list[WebhookResponse]:
    """Return all webhooks for a tenant (secret never included)."""
    webhooks = (
        db.query(Webhook)
        .filter(Webhook.tenant_id == tenant_id)
        .order_by(Webhook.created_at)
        .all()
    )
    return [_to_response(w) for w in webhooks]


@router.get("/{webhook_id}", response_model=WebhookResponse)
def get_webhook(
    webhook_id: str,
    db: Session = Depends(get_session),  # noqa: B008
) -> WebhookResponse:
    """Return a single webhook by ID (secret never included)."""
    webhook = db.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")
    return _to_response(webhook)


@router.put("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    db: Session = Depends(get_session),  # noqa: B008
) -> WebhookResponse:
    """Update mutable webhook fields."""
    webhook = db.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")

    if body.url is not None:
        webhook.url = body.url
    if body.secret is not None:
        ciphertext, nonce = seal(body.secret)
        webhook.secret_ciphertext = ciphertext
        webhook.secret_nonce = nonce
    if body.active is not None:
        webhook.active = body.active

    db.commit()
    db.refresh(webhook)
    return _to_response(webhook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: str,
    db: Session = Depends(get_session),  # noqa: B008
) -> None:
    """Delete a webhook."""
    webhook = db.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")
    db.delete(webhook)
    db.commit()
