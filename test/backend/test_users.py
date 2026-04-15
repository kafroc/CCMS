import pytest
from conftest import auth
from app.core.database import AsyncSessionLocal
from app.core.auth import hash_password
from app.models.user import User


@pytest.mark.asyncio
async def test_admin_can_list_users(client, admin_token):
    res = await client.get("/api/users", headers=auth(admin_token))
    assert res.status_code == 200
    users = res.json()["data"]
    assert any(u["username"] == "admin" for u in users)


@pytest.mark.asyncio
async def test_non_admin_cannot_list_users(client, user_token):
    res = await client.get("/api/users", headers=auth(user_token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_user(client, admin_token):
    res = await client.post(
        "/api/users",
        headers=auth(admin_token),
        json={"username": "bob", "password": "BobPw!2345", "role": "user", "toe_permissions": []},
    )
    assert res.status_code == 200
    created = res.json()["data"]
    assert created["username"] == "bob"
    assert created["role"] == "user"


@pytest.mark.asyncio
async def test_user_cannot_create_user(client, user_token):
    res = await client.post(
        "/api/users",
        headers=auth(user_token),
        json={"username": "eve", "password": "EvePw!2345", "role": "user"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_force_password_change_flow(client):
    """User with must_change_password=True logs in, changes password,
    the flag must then be cleared."""
    # Seed a user who has been handed a temporary password.
    async with AsyncSessionLocal() as db:
        db.add(User(
            username="carol",
            password_hash=hash_password("TempPw!2345"),
            role="user",
            must_change_password=True,
        ))
        await db.commit()

    # Login reports the flag.
    res = await client.post(
        "/api/auth/login",
        data={"username": "carol", "password": "TempPw!2345"},
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["user"]["must_change_password"] is True
    token = body["access_token"]
    user_id = body["user"]["id"]

    # Change password.
    res = await client.put(
        f"/api/users/{user_id}/password",
        headers=auth(token),
        json={"old_password": "TempPw!2345", "new_password": "CarolNewPw!9876"},
    )
    assert res.status_code == 200

    # /me no longer flags the user.
    res = await client.get("/api/auth/me", headers=auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["must_change_password"] is False


@pytest.mark.asyncio
async def test_new_password_must_differ(client, admin_token, admin_user):
    res = await client.put(
        f"/api/users/{admin_user.id}/password",
        headers=auth(admin_token),
        json={"old_password": "AdminPw!2345", "new_password": "AdminPw!2345"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_wrong_old_password_rejected(client, admin_token, admin_user):
    res = await client.put(
        f"/api/users/{admin_user.id}/password",
        headers=auth(admin_token),
        json={"old_password": "nope", "new_password": "SomethingNew!99"},
    )
    assert res.status_code == 400
