import pytest


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["code"] == 0
    assert res.json()["data"]["version"]
