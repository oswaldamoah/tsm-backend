"""
Auth flow tests. Runs against a throwaway SQLite database - no server needed.

    pip install pytest
    pytest test_auth.py -q
"""
import os
import re
import tempfile

_db_file = os.path.join(tempfile.mkdtemp(), "auth_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["SIGNUP_ACCESS_CODE"] = "member-phrase"
os.environ["ADMIN_SIGNUP_ACCESS_CODE"] = "admin-phrase"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.pop("RESEND_API_KEY", None)  # print emails instead of sending

from fastapi.testclient import TestClient  # noqa: E402

import mailer  # noqa: E402
from app import app  # noqa: E402

sent = []
mailer.send_email = lambda to, subject, html, text: sent.append((to, text)) or True


def signup(client, email, username, password="correct-horse", code="member-phrase"):
    return client.post(
        "/auth/signup",
        json={"email": email, "username": username, "password": password, "accessCode": code},
    )


def test_full_auth_flow():
    with TestClient(app) as client:
        assert client.get("/auth/config").json() == {"signupEnabled": True}

        # Access phrase is required and decides the role
        assert signup(client, "a@example.com", "alice", code="nope").status_code == 403
        r = signup(client, "Alice@Example.com", "alice")
        assert r.status_code == 201 and r.json()["role"] == "manager"
        r = signup(client, "boss@example.com", "boss", code="admin-phrase")
        assert r.json()["role"] == "admin"

        # Duplicates and weak input are rejected
        assert signup(client, "alice@example.com", "alice2").status_code == 409
        assert signup(client, "x@example.com", "alice").status_code == 409
        assert signup(client, "not-an-email", "carol").status_code == 422
        assert signup(client, "c@example.com", "carol", password="short").status_code == 422

        # Email sign-in is case-insensitive; wrong password fails
        assert client.post("/auth/login", json={"email": "alice@example.com", "password": "bad-password"}).status_code == 401
        token = client.post("/auth/login", json={"email": " ALICE@example.com", "password": "correct-horse"}).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # Data needs a session
        assert client.get("/sites").status_code == 401
        assert client.get("/sites", headers=auth).status_code == 200
        assert client.get("/auth/me", headers=auth).json()["email"] == "alice@example.com"

        # Forgot password: same answer for unknown emails, link emailed for real ones
        unknown = client.post("/auth/forgot-password", json={"email": "ghost@example.com"})
        known = client.post("/auth/forgot-password", json={"email": "alice@example.com"})
        assert unknown.json() == known.json()
        assert len(sent) == 1
        reset_token = re.search(r"reset_token=([\w-]+)", sent[0][1]).group(1)

        # Reset works once, signs in, and revokes the old session
        r = client.post("/auth/reset-password", json={"token": reset_token, "password": "brand-new-pass"})
        assert r.status_code == 200
        assert client.post("/auth/reset-password", json={"token": reset_token, "password": "another-pass"}).status_code == 400
        assert client.get("/sites", headers=auth).status_code == 401
        assert client.post("/auth/login", json={"email": "alice@example.com", "password": "brand-new-pass"}).status_code == 200


if __name__ == "__main__":
    test_full_auth_flow()
    print("All auth checks passed.")
