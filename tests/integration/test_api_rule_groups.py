"""Integration tests for composite rule group CRUD endpoints."""

import pytest

from src.api.deps import create_access_token


@pytest.mark.integration
class TestRuleGroupCRUD:
    async def test_create_rule_group(self, client, auth_headers):
        response = await client.post("/rule-groups", json={
            "latitude": -34.6037,
            "longitude": -58.3816,
            "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "wind_speed", "operator": "lt", "threshold_value": 10.0},
            ],
        }, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["logic"] == "and"
        assert len(data["conditions"]) == 2
        assert data["conditions"][0]["metric_type"] == "temperature"
        assert data["conditions"][1]["metric_type"] == "wind_speed"
        assert "location_h3_index" in data

    async def test_create_rule_group_or_logic(self, client, auth_headers):
        response = await client.post("/rule-groups", json={
            "latitude": -34.6037,
            "longitude": -58.3816,
            "logic": "or",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 40.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 10.0},
            ],
        }, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["logic"] == "or"

    async def test_create_rule_group_min_conditions(self, client, auth_headers):
        """Must have at least 2 conditions."""
        response = await client.post("/rule-groups", json={
            "latitude": 0.0,
            "longitude": 0.0,
            "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
            ],
        }, headers=auth_headers)
        assert response.status_code == 422

    async def test_list_rule_groups(self, client, auth_headers):
        await client.post("/rule-groups", json={
            "latitude": -34.6037, "longitude": -58.3816, "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0},
            ],
        }, headers=auth_headers)

        response = await client.get("/rule-groups", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()) >= 1

    async def test_get_rule_group(self, client, auth_headers):
        create_resp = await client.post("/rule-groups", json={
            "latitude": -34.6037, "longitude": -58.3816, "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0},
            ],
        }, headers=auth_headers)
        group_id = create_resp.json()["id"]

        response = await client.get(f"/rule-groups/{group_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == group_id
        assert len(response.json()["conditions"]) == 2

    async def test_update_rule_group_conditions(self, client, auth_headers):
        create_resp = await client.post("/rule-groups", json={
            "latitude": -34.6037, "longitude": -58.3816, "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0},
            ],
        }, headers=auth_headers)
        group_id = create_resp.json()["id"]

        response = await client.put(f"/rule-groups/{group_id}", json={
            "logic": "or",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 35.0},
                {"metric_type": "wind_speed", "operator": "gte", "threshold_value": 50.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 15.0},
            ],
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["logic"] == "or"
        assert len(data["conditions"]) == 3

    async def test_delete_rule_group(self, client, auth_headers):
        create_resp = await client.post("/rule-groups", json={
            "latitude": -34.6037, "longitude": -58.3816, "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0},
            ],
        }, headers=auth_headers)
        group_id = create_resp.json()["id"]

        response = await client.delete(f"/rule-groups/{group_id}", headers=auth_headers)
        assert response.status_code == 204

        response = await client.get(f"/rule-groups/{group_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_no_auth(self, client):
        response = await client.post("/rule-groups", json={
            "latitude": 0.0, "longitude": 0.0, "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0},
            ],
        })
        assert response.status_code == 403


@pytest.mark.integration
class TestRuleGroupIDOR:
    async def test_cannot_read_other_users_group(self, client, test_user):
        headers_a = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
        create_resp = await client.post("/rule-groups", json={
            "latitude": -34.6037, "longitude": -58.3816, "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0},
            ],
        }, headers=headers_a)
        group_id = create_resp.json()["id"]

        headers_b = {"Authorization": f"Bearer {create_access_token(99999)}"}
        response = await client.get(f"/rule-groups/{group_id}", headers=headers_b)
        assert response.status_code == 404

    async def test_cannot_delete_other_users_group(self, client, test_user):
        headers_a = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
        create_resp = await client.post("/rule-groups", json={
            "latitude": -34.6037, "longitude": -58.3816, "logic": "and",
            "conditions": [
                {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
                {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0},
            ],
        }, headers=headers_a)
        group_id = create_resp.json()["id"]

        headers_b = {"Authorization": f"Bearer {create_access_token(99999)}"}
        response = await client.delete(f"/rule-groups/{group_id}", headers=headers_b)
        assert response.status_code == 404
