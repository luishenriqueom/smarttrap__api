GATEWAY = {"X-API-Key": "test-gateway-key"}
JPEG = b"\xff\xd8\xff\xd9"


def login(client, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def login_demo(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/demo")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
