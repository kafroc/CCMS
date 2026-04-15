import pytest
from conftest import auth


@pytest.mark.asyncio
async def test_settings_admin_only(client, user_token):
    res = await client.get("/api/system/settings", headers=auth(user_token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(client, admin_token):
    res = await client.get("/api/system/settings", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "pdf_parse_timeout_seconds" in data
    assert data["pdf_parse_timeout_seconds"]["value"] == "300"


@pytest.mark.asyncio
async def test_update_settings(client, admin_token):
    res = await client.patch(
        "/api/system/settings",
        headers=auth(admin_token),
        json={"pdf_parse_timeout_seconds": 600},
    )
    assert res.status_code == 200
    assert res.json()["data"]["pdf_parse_timeout_seconds"]["value"] == "600"


@pytest.mark.asyncio
async def test_update_settings_validates_bounds(client, admin_token):
    res = await client.patch(
        "/api/system/settings",
        headers=auth(admin_token),
        json={"pdf_parse_timeout_seconds": 10},  # below min 30
    )
    assert res.status_code == 400
