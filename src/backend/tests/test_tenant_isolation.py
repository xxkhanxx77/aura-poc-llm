"""Tests for tenant isolation logic -- the most critical security property."""

from uuid import UUID, uuid4

import pytest
from jose import jwt

from app.core.auth import TenantContext, get_tenant
from app.core.config import settings
from app.services.cache_service import _cache_key, hash_jd


def _make_token(tenant_id: str, user_id: str = "user-1", role: str = "admin") -> str:
    return jwt.encode(
        {"tenant_id": tenant_id, "sub": user_id, "role": role},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


class TestTenantAuth:
    def test_valid_token_extracts_tenant(self):
        tid = str(uuid4())
        token = _make_token(tid)

        class FakeCreds:
            credentials = token

        ctx = get_tenant(FakeCreds())
        assert ctx.tenant_id == UUID(tid)
        assert ctx.user_id == "user-1"

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException

        class FakeCreds:
            credentials = "invalid.jwt.token"

        with pytest.raises(HTTPException) as exc_info:
            get_tenant(FakeCreds())
        assert exc_info.value.status_code == 401

    def test_missing_tenant_id_raises_401(self):
        from fastapi import HTTPException

        token = jwt.encode(
            {"sub": "user-1"},  # no tenant_id
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

        class FakeCreds:
            credentials = token

        with pytest.raises(HTTPException) as exc_info:
            get_tenant(FakeCreds())
        assert exc_info.value.status_code == 401


class TestCacheIsolation:
    def test_cache_keys_namespaced_by_tenant(self):
        """Two tenants scoring the same job/resume must not share cache."""
        tenant_a = uuid4()
        tenant_b = uuid4()
        job_id = uuid4()
        resume_id = uuid4()
        jd_hash = hash_jd("some job description")

        key_a = _cache_key(tenant_a, job_id, resume_id, jd_hash)
        key_b = _cache_key(tenant_b, job_id, resume_id, jd_hash)

        assert key_a != key_b
        assert str(tenant_a) in key_a
        assert str(tenant_b) in key_b

    def test_jd_hash_changes_invalidate_cache(self):
        tid = uuid4()
        job_id = uuid4()
        resume_id = uuid4()

        hash_v1 = hash_jd("Looking for a Python developer")
        hash_v2 = hash_jd("Looking for a Python developer with K8s experience")

        key_v1 = _cache_key(tid, job_id, resume_id, hash_v1)
        key_v2 = _cache_key(tid, job_id, resume_id, hash_v2)

        assert key_v1 != key_v2
