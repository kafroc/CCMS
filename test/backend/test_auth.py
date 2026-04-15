import pytest
from conftest import auth


@pytest.mark.asyncio
async def test_login_ok(client, admin_user):
    res = await client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "AdminPw!2345"},
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"
    assert body["user"]["must_change_password"] is False


@pytest.mark.asyncio
async def test_login_wrong_password(client, admin_user):
    res = await client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "wrong"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    res = await client.post(
        "/api/auth/login",
        data={"username": "nobody", "password": "whatever"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_token(client):
    res = await client.get("/api/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client, admin_token):
    res = await client.get("/api/auth/me", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["username"] == "admin"
    assert "must_change_password" in data


@pytest.mark.asyncio
async def test_me_with_tampered_token(client):
    res = await client.get("/api/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert res.status_code == 401
