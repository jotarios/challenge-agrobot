"""Integration tests for authentication endpoints."""

import pytest


@pytest.mark.integration
class TestRegister:
    async def test_register_success(self, client):
        response = await client.post("/auth/register", json={
            "email": "new@example.com",
            "password": "password123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert "id" in data

    async def test_register_duplicate_email(self, client, test_user):
        response = await client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "password123",
        })
        assert response.status_code == 409

    async def test_register_invalid_email(self, client):
        response = await client.post("/auth/register", json={
            "email": "not-email",
            "password": "password123",
        })
        assert response.status_code == 422

    async def test_register_short_password(self, client):
        response = await client.post("/auth/register", json={
            "email": "new@example.com",
            "password": "short",
        })
        assert response.status_code == 422


@pytest.mark.integration
class TestLogin:
    async def test_login_success(self, client, test_user):
        response = await client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "password123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client, test_user):
        response = await client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "wrong_password",
        })
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client):
        response = await client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "password123",
        })
        assert response.status_code == 401
