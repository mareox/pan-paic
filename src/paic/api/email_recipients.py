"""Email recipient CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from paic.api.schemas.email_recipient import EmailRecipientCreate, EmailRecipientResponse
from paic.db.models import EmailRecipient, Tenant
from paic.db.session import get_session

router = APIRouter(prefix="/api/email-recipients", tags=["email-recipients"])


def _to_response(recipient: EmailRecipient) -> EmailRecipientResponse:
    return EmailRecipientResponse.model_validate(recipient)


@router.post("", response_model=EmailRecipientResponse, status_code=status.HTTP_201_CREATED)
def create_email_recipient(
    body: EmailRecipientCreate,
    db: Session = Depends(get_session),  # noqa: B008
) -> EmailRecipientResponse:
    """Register an email address to receive diff alerts for a tenant."""
    tenant = db.get(Tenant, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    recipient = EmailRecipient(
        tenant_id=body.tenant_id,
        address=body.address,
        active=body.active,
    )
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return _to_response(recipient)


@router.get("", response_model=list[EmailRecipientResponse])
def list_email_recipients(
    tenant_id: str,
    db: Session = Depends(get_session),  # noqa: B008
) -> list[EmailRecipientResponse]:
    """List all email recipients for a tenant."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    recipients = (
        db.query(EmailRecipient)
        .filter(EmailRecipient.tenant_id == tenant_id)
        .order_by(EmailRecipient.created_at)
        .all()
    )
    return [_to_response(r) for r in recipients]


@router.get("/{recipient_id}", response_model=EmailRecipientResponse)
def get_email_recipient(
    recipient_id: str,
    db: Session = Depends(get_session),  # noqa: B008
) -> EmailRecipientResponse:
    """Fetch a single email recipient by ID."""
    recipient = db.get(EmailRecipient, recipient_id)
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Email recipient not found."
        )
    return _to_response(recipient)


@router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_email_recipient(
    recipient_id: str,
    db: Session = Depends(get_session),  # noqa: B008
) -> None:
    """Remove an email recipient."""
    recipient = db.get(EmailRecipient, recipient_id)
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Email recipient not found."
        )
    db.delete(recipient)
    db.commit()
