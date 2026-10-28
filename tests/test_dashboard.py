def test_dashboard_is_served(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "Guardrail Gateway" in r.text


def test_root_redirects_to_dashboard(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/dashboard"
