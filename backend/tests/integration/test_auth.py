import pytest
from httpx import AsyncClient


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        payload = {"username": "testuser", "password": "password123", "email": "test@example.com"}
        resp = await client.post("/auth/register", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, client: AsyncClient):
        payload = {"username": "dupuser", "password": "password123", "email": "dup1@example.com"}
        await client.post("/auth/register", json=payload)
        resp = await client.post("/auth/register", json=payload)
        assert resp.status_code == 409
        assert resp.json()["code"] == "USER_EXISTS"

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient):
        payload1 = {"username": "user1", "password": "password123", "email": "same@example.com"}
        payload2 = {"username": "user2", "password": "password123", "email": "same@example.com"}
        await client.post("/auth/register", json=payload1)
        resp = await client.post("/auth/register", json=payload2)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_short_username(self, client: AsyncClient):
        payload = {"username": "ab", "password": "password123", "email": "ab@example.com"}
        resp = await client.post("/auth/register", json=payload)
        assert resp.status_code == 422


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient):
        register_payload = {"username": "loginuser", "password": "password123", "email": "login@example.com"}
        await client.post("/auth/register", json=register_payload)
        login_payload = {"username": "loginuser", "password": "password123"}
        resp = await client.post("/auth/login", json=login_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient):
        register_payload = {"username": "wrongpw", "password": "correctpw", "email": "wrongpw@example.com"}
        await client.post("/auth/register", json=register_payload)
        login_payload = {"username": "wrongpw", "password": "wrongpw"}
        resp = await client.post("/auth/login", json=login_payload)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        payload = {"username": "nobody", "password": "password123"}
        resp = await client.post("/auth/login", json=payload)
        assert resp.status_code == 401


class TestGetMe:
    @pytest.mark.asyncio
    async def test_get_me_success(self, client: AsyncClient):
        register_payload = {"username": "meuser", "password": "password123", "email": "me@example.com"}
        await client.post("/auth/register", json=register_payload)
        login_payload = {"username": "meuser", "password": "password123"}
        login_resp = await client.post("/auth/login", json=login_payload)
        token = login_resp.json()["access_token"]
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "meuser"

    @pytest.mark.asyncio
    async def test_get_me_no_token(self, client: AsyncClient):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client: AsyncClient):
        resp = await client.get("/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401


class TestRefresh:
    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient):
        register_payload = {"username": "refreshuser", "password": "password123", "email": "refresh@example.com"}
        await client.post("/auth/register", json=register_payload)
        login_payload = {"username": "refreshuser", "password": "password123"}
        login_resp = await client.post("/auth/login", json=login_payload)
        refresh_token = login_resp.json()["refresh_token"]
        resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()
        assert "refresh_token" in resp.json()

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post("/auth/refresh", json={"refresh_token": "invalid"})
        assert resp.status_code == 401
