"""Tenant CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from paic.api.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantUpdate,
    TestConnectionResponse,
)
from paic.core.crypto import seal, unseal
from paic.db.models import Tenant
from paic.db.session import get_session

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


def _to_response(tenant: Tenant) -> TenantResponse:
    return TenantResponse.model_validate(tenant)


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    db: Session = Depends(get_session),  # noqa: B008
) -> TenantResponse:
    """Create a new tenant, storing the API key encrypted at rest."""
    existing = db.query(Tenant).filter(Tenant.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with name '{body.name}' already exists.",
        )

    ciphertext, nonce = seal(body.api_key)
    tenant = Tenant(
        name=body.name,
        api_key_ciphertext=ciphertext,
        api_key_nonce=nonce,
        base_url=body.base_url,
        poll_interval_sec=body.poll_interval_sec,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return _to_response(tenant)


@router.get("", response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_session)) -> list[TenantResponse]:  # noqa: B008
    """Return all tenants (no API keys)."""
    tenants = db.query(Tenant).order_by(Tenant.created_at).all()
    return [_to_response(t) for t in tenants]


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, db: Session = Depends(get_session)) -> TenantResponse:  # noqa: B008
    """Return a single tenant by ID."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return _to_response(tenant)


@router.put("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    db: Session = Depends(get_session),  # noqa: B008
) -> TenantResponse:
    """Update mutable tenant fields."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    if body.name is not None:
        tenant.name = body.name
    if body.api_key is not None:
        ciphertext, nonce = seal(body.api_key)
        tenant.api_key_ciphertext = ciphertext
        tenant.api_key_nonce = nonce
    if body.base_url is not None:
        tenant.base_url = body.base_url
    if body.poll_interval_sec is not None:
        tenant.poll_interval_sec = body.poll_interval_sec

    db.commit()
    db.refresh(tenant)
    return _to_response(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(tenant_id: str, db: Session = Depends(get_session)) -> None:  # noqa: B008
    """Delete a tenant."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    db.delete(tenant)
    db.commit()


@router.post("/{tenant_id}/test-connection", response_model=TestConnectionResponse)
def test_connection(
    tenant_id: str,
    db: Session = Depends(get_session),  # noqa: B008
) -> TestConnectionResponse:
    """Verify stored credentials can decrypt and are non-empty."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    try:
        api_key = unseal(tenant.api_key_ciphertext, tenant.api_key_nonce)
        if not api_key:
            return TestConnectionResponse(success=False, detail="Stored API key is empty.")
        return TestConnectionResponse(success=True, detail="Credentials decrypted successfully.")
    except Exception as exc:  # noqa: BLE001
        return TestConnectionResponse(success=False, detail=f"Decryption failed: {exc}")
