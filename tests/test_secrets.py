from app.guards.secrets import find_secrets


def kinds(text):
    return [s.label for s in find_secrets(text, 3.0)]


def test_known_formats():
    assert kinds("AKIAIOSFODNN7EXAMPLE") == ["AWS_ACCESS_KEY"]
    assert kinds("token ghp_" + "a1B2" * 9) == ["GITHUB_TOKEN"]
    assert kinds("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----") == ["PRIVATE_KEY"]


def test_entropy_filters_weak_assignments():
    assert kinds("password = Xk9#pLq2!vB") == ["ASSIGNED_SECRET"]
    assert kinds("password = aaaaaaaa") == []
