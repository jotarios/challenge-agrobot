"""Integration tests for health and status endpoints."""

import pytest


@pytest.mark.integration
class TestHealth:
    async def test_health_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["checks"]["db"] == "ok"


@pytest.mark.integration
class TestStatus:
    async def test_status_requires_auth(self, client):
        response = await client.get("/status")
        assert response.status_code == 403

    async def test_status_requires_admin(self, client, auth_headers):
        response = await client.get("/status", headers=auth_headers)
        assert response.status_code == 403

    async def test_status_admin_access(self, client, admin_headers):
        response = await client.get("/status", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
