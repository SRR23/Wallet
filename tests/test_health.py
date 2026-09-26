def test_health_check(api_client):
    """The process is up. This does not cover wallet behavior."""
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
