"""Unit tests for the Tenant ORM model."""

import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from paic.db.base import Base
from paic.db.models import Tenant


@pytest.fixture()
def session():
    """In-memory SQLite session for model tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    Base.metadata.drop_all(engine)


def test_tenant_table_name() -> None:
    assert Tenant.__tablename__ == "tenants"


def test_tenant_column_names() -> None:
    """All required columns exist on the model."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("tenants")}
    expected = {
        "id",
        "name",
        "api_key_ciphertext",
        "api_key_nonce",
        "base_url",
        "poll_interval_sec",
        "last_fetch_at",
        "last_fetch_status",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols)


def test_tenant_defaults(session) -> None:
    """Tenant default values are applied on insert."""
    ciphertext = b"\x00" * 32
    nonce = b"\x01" * 12
    tenant = Tenant(
        name="acme",
        api_key_ciphertext=ciphertext,
        api_key_nonce=nonce,
    )
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    assert tenant.id is not None
    assert len(str(tenant.id)) == 36  # UUID string
    assert tenant.base_url == "https://api.prod.datapath.prismaaccess.com"
    assert tenant.poll_interval_sec == 900
    assert tenant.last_fetch_at is None
    assert tenant.last_fetch_status is None
    # SQLite server_default sets created_at; check it's not None
    assert tenant.created_at is not None


def test_tenant_name_unique(session) -> None:
    """Duplicate tenant names are rejected by DB unique constraint."""
    from sqlalchemy.exc import IntegrityError

    ciphertext = b"\x00" * 32
    nonce = b"\x01" * 12

    t1 = Tenant(name="dup", api_key_ciphertext=ciphertext, api_key_nonce=nonce)
    t2 = Tenant(name="dup", api_key_ciphertext=ciphertext, api_key_nonce=nonce)
    session.add(t1)
    session.commit()

    session.add(t2)
    with pytest.raises(IntegrityError):
        session.commit()


def test_tenant_id_is_uuid_string(session) -> None:
    """Auto-generated id is a valid UUID string."""
    t = Tenant(
        name="uuid-check",
        api_key_ciphertext=b"x" * 32,
        api_key_nonce=b"y" * 12,
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    # Should not raise
    uuid.UUID(t.id)


def test_tenant_stores_binary_blobs(session) -> None:
    """LargeBinary columns round-trip correctly."""
    ct = bytes(range(48))
    nonce = bytes(range(12))
    t = Tenant(name="blobs", api_key_ciphertext=ct, api_key_nonce=nonce)
    session.add(t)
    session.commit()
    session.refresh(t)
    assert t.api_key_ciphertext == ct
    assert t.api_key_nonce == nonce
