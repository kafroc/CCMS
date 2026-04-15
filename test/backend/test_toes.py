"""Smoke test for the core TOE CRUD flow — exercised end-to-end
via the HTTP surface to catch obvious regressions in routing,
permissions, and serialization."""
import pytest
from conftest import auth


@pytest.mark.asyncio
async def test_toe_create_list_update_delete(client, admin_token):
    # Create
    res = await client.post(
        "/api/toes",
        headers=auth(admin_token),
        json={"name": "Router-Alpha", "version": "1.0", "toe_type": "hardware"},
    )
    assert res.status_code == 200, res.text
    toe = res.json()["data"]
    toe_id = toe["id"]
    assert toe["name"] == "Router-Alpha"

    # List — `/api/toes` returns a list.
    res = await client.get("/api/toes", headers=auth(admin_token))
    assert res.status_code == 200
    items = res.json()["data"]
    assert isinstance(items, list)
    assert any(t["id"] == toe_id for t in items)

    # Detail
    res = await client.get(f"/api/toes/{toe_id}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["id"] == toe_id

    # Soft delete
    res = await client.delete(f"/api/toes/{toe_id}", headers=auth(admin_token))
    assert res.status_code == 200

    # Gone from list
    res = await client.get("/api/toes", headers=auth(admin_token))
    items = res.json()["data"]
    assert not any(t["id"] == toe_id for t in items)


@pytest.mark.asyncio
async def test_toe_rejects_invalid_type(client, admin_token):
    res = await client.post(
        "/api/toes",
        headers=auth(admin_token),
        json={"name": "X", "toe_type": "firmware"},  # not an allowed value
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_toe_requires_auth(client):
    res = await client.get("/api/toes")
    assert res.status_code == 401
