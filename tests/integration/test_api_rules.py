"""Integration tests for rule CRUD endpoints with IDOR prevention."""

import pytest

from src.api.deps import create_access_token


@pytest.mark.integration
class TestRuleCRUD:
    async def test_create_rule(self, client, auth_headers):
        response = await client.post("/rules", json={
            "latitude": -34.6037,
            "longitude": -58.3816,
            "metric_type": "temperature",
            "operator": "gt",
            "threshold_value": 35.0,
        }, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["metric_type"] == "temperature"
        assert data["operator"] == "gt"
        assert data["threshold_value"] == 35.0
        assert "location_h3_index" in data

    async def test_list_rules(self, client, auth_headers):
        # Create a rule first
        await client.post("/rules", json={
            "latitude": -34.6037, "longitude": -58.3816,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        }, headers=auth_headers)

        response = await client.get("/rules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_get_rule(self, client, auth_headers):
        create_resp = await client.post("/rules", json={
            "latitude": -34.6037, "longitude": -58.3816,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        }, headers=auth_headers)
        rule_id = create_resp.json()["id"]

        response = await client.get(f"/rules/{rule_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == rule_id

    async def test_update_rule(self, client, auth_headers):
        create_resp = await client.post("/rules", json={
            "latitude": -34.6037, "longitude": -58.3816,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        }, headers=auth_headers)
        rule_id = create_resp.json()["id"]

        response = await client.put(f"/rules/{rule_id}", json={
            "threshold_value": 40.0,
        }, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["threshold_value"] == 40.0

    async def test_delete_rule(self, client, auth_headers):
        create_resp = await client.post("/rules", json={
            "latitude": -34.6037, "longitude": -58.3816,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        }, headers=auth_headers)
        rule_id = create_resp.json()["id"]

        response = await client.delete(f"/rules/{rule_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/rules/{rule_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_list_rules_empty(self, client, auth_headers):
        response = await client.get("/rules", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_nonexistent_rule(self, client, auth_headers):
        response = await client.get("/rules/99999", headers=auth_headers)
        assert response.status_code == 404

    async def test_create_rule_no_auth(self, client):
        response = await client.post("/rules", json={
            "latitude": 0.0, "longitude": 0.0,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        })
        assert response.status_code == 403


@pytest.mark.integration
class TestIDORPrevention:
    """Verify user A cannot access user B's rules."""

    async def test_cannot_read_other_users_rule(self, client, test_user, db_session):
        # Create a rule as test_user
        headers_a = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
        create_resp = await client.post("/rules", json={
            "latitude": -34.6037, "longitude": -58.3816,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        }, headers=headers_a)
        rule_id = create_resp.json()["id"]

        # Try to access as a different user (id=99999)
        headers_b = {"Authorization": f"Bearer {create_access_token(99999)}"}
        response = await client.get(f"/rules/{rule_id}", headers=headers_b)
        assert response.status_code == 404

    async def test_cannot_delete_other_users_rule(self, client, test_user, db_session):
        headers_a = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
        create_resp = await client.post("/rules", json={
            "latitude": -34.6037, "longitude": -58.3816,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        }, headers=headers_a)
        rule_id = create_resp.json()["id"]

        headers_b = {"Authorization": f"Bearer {create_access_token(99999)}"}
        response = await client.delete(f"/rules/{rule_id}", headers=headers_b)
        assert response.status_code == 404

    async def test_cannot_update_other_users_rule(self, client, test_user, db_session):
        headers_a = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
        create_resp = await client.post("/rules", json={
            "latitude": -34.6037, "longitude": -58.3816,
            "metric_type": "temperature", "operator": "gt", "threshold_value": 35.0,
        }, headers=headers_a)
        rule_id = create_resp.json()["id"]

        headers_b = {"Authorization": f"Bearer {create_access_token(99999)}"}
        response = await client.put(f"/rules/{rule_id}", json={
            "threshold_value": 99.0,
        }, headers=headers_b)
        assert response.status_code == 404
