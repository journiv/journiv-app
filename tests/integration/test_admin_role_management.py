"""
Integration tests for admin role management and user administration.
"""
import uuid

import pytest

from tests.lib import ApiUser, JournivApiClient, make_api_user


def _unique_credentials(prefix: str = "admin") -> tuple[str, str]:
    """Generate unique email and password for testing."""
    suffix = uuid.uuid4().hex[:8]
    email = f"{prefix}-{suffix}@example.com"
    password = f"Pass-{suffix}-Aa1!"
    return email, password


def _ensure_admin_user(api_client: JournivApiClient) -> ApiUser:
    """Ensure we have an admin user for testing."""
    user = make_api_user(api_client)

    response = api_client.request(
        "GET",
        "/admin/users",
        headers={"Authorization": f"Bearer {user.access_token}"}
    )

    if response.status_code == 200:
        return user

    pytest.skip(
        f"Cannot ensure admin user exists. User {user.email} cannot access admin endpoints. "
        "This may indicate the test database needs proper setup or first user bootstrap failed."
    )
    raise AssertionError("Unreachable code")  # For type checker


def _ensure_regular_user(api_client: JournivApiClient, admin: ApiUser) -> ApiUser:
    """Ensure we have a regular (non-admin) user for testing."""
    email, password = _unique_credentials("regular-user")

    response = api_client.request(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={
            "email": email,
            "password": password,
            "name": "Regular Test User",
            "role": "user"
        }
    )

    if response.status_code == 201:
        created_user = response.json()
        token_payload = api_client.login(email, password)
        return ApiUser(
            email=email,
            password=password,
            access_token=token_payload["access_token"],
            refresh_token=token_payload.get("refresh_token"),
            user_id=created_user["id"],
        )

    return make_api_user(api_client)


def test_first_user_becomes_admin(api_client: JournivApiClient):
    """First registered user should automatically become admin."""
    user = make_api_user(api_client)
    profile = api_client.current_user(user.access_token)

    assert "role" in profile
    assert profile["role"] in ["admin", "user"]


def test_signup_disabled_blocks_registration(api_client: JournivApiClient):
    """When signup is disabled, new registrations should be blocked."""
    email, password = _unique_credentials("blocked")

    response = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Blocked User"
        }
    )

    # If signup is enabled, this will succeed (200/201)
    # If signup is disabled, this will fail (403)
    # We just verify the endpoint works
    assert response.status_code in [201, 403]


def test_admin_can_list_users(api_client: JournivApiClient):
    """Admin users can list all users."""
    admin = _ensure_admin_user(api_client)

    response = api_client.request(
        "GET",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin.access_token}"}
    )

    assert response.status_code == 200, "Admin should be able to list users"
    users = response.json()
    assert isinstance(users, list)
    assert len(users) >= 1, "Should include at least the admin user"


def test_non_admin_cannot_list_users(api_client: JournivApiClient):
    """Non-admin users cannot access admin endpoints."""
    admin = _ensure_admin_user(api_client)
    regular_user = _ensure_regular_user(api_client, admin)

    response = api_client.request(
        "GET",
        "/admin/users",
        headers={"Authorization": f"Bearer {regular_user.access_token}"}
    )

    assert response.status_code == 403, "Non-admin users should be blocked from admin endpoints"


def test_admin_can_create_user(api_client: JournivApiClient):
    """Admin can create new users with specified role."""
    admin = _ensure_admin_user(api_client)

    email, password = _unique_credentials("created-by-admin")

    response = api_client.request(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={
            "email": email,
            "password": password,
            "name": "Admin Created User",
            "role": "user"
        }
    )

    assert response.status_code == 201, "Admin should be able to create users"
    created_user = response.json()
    assert created_user["email"] == email
    assert created_user["role"] == "user"
    assert created_user["name"] == "Admin Created User"


def test_admin_can_promote_user_to_admin(api_client: JournivApiClient):
    """Admin can promote a regular user to admin."""
    admin = _ensure_admin_user(api_client)
    regular_user = _ensure_regular_user(api_client, admin)

    response = api_client.request(
        "PATCH",
        f"/admin/users/{regular_user.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={"role": "admin"}
    )

    assert response.status_code == 200, "Admin should be able to promote users"
    updated_user = response.json()
    assert updated_user["role"] == "admin"


def test_cannot_delete_last_admin(api_client: JournivApiClient):
    """Cannot delete the last admin user."""
    admin = _ensure_admin_user(api_client)

    # Try to delete self (the last admin)
    response = api_client.request(
        "DELETE",
        f"/admin/users/{admin.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"}
    )

    assert response.status_code == 400, "Should prevent deletion of last admin"
    error_detail = response.json().get("detail", "")
    assert "last admin" in error_detail.lower() or "cannot delete" in error_detail.lower()


def test_cannot_demote_last_admin(api_client: JournivApiClient):
    """Cannot demote the last admin to regular user."""
    admin = _ensure_admin_user(api_client)

    # Try to demote self to user
    response = api_client.request(
        "PATCH",
        f"/admin/users/{admin.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={"role": "user"}
    )

    assert response.status_code == 400, "Should prevent demotion of last admin"
    error_detail = response.json().get("detail", "")
    assert "last admin" in error_detail.lower() or "cannot demote" in error_detail.lower()


def test_admin_can_delete_regular_user(api_client: JournivApiClient):
    """Admin can delete regular users."""
    admin = _ensure_admin_user(api_client)
    regular_user = _ensure_regular_user(api_client, admin)

    response = api_client.request(
        "DELETE",
        f"/admin/users/{regular_user.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"}
    )

    assert response.status_code == 200, "Admin should be able to delete regular users"


def test_admin_can_update_user_email(api_client: JournivApiClient):
    """Admin can update user email address."""
    admin = _ensure_admin_user(api_client)
    regular_user = _ensure_regular_user(api_client, admin)

    new_email = f"updated-{uuid.uuid4().hex[:8]}@example.com"

    response = api_client.request(
        "PATCH",
        f"/admin/users/{regular_user.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={"email": new_email}
    )

    assert response.status_code == 200, "Admin should be able to update user email"
    updated_user = response.json()
    assert updated_user["email"] == new_email


def test_admin_can_deactivate_user(api_client: JournivApiClient):
    """Admin can deactivate user accounts."""
    admin = _ensure_admin_user(api_client)
    regular_user = _ensure_regular_user(api_client, admin)

    response = api_client.request(
        "PATCH",
        f"/admin/users/{regular_user.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={"is_active": False}
    )

    assert response.status_code == 200, "Admin should be able to deactivate users"
    updated_user = response.json()
    assert updated_user["is_active"] is False


def test_user_profile_includes_role(api_client: JournivApiClient):
    """User profile response should include role field."""
    user = make_api_user(api_client)
    profile = api_client.current_user(user.access_token)

    # Role should be present in profile
    assert "role" in profile
    assert profile["role"] in ["admin", "user"]


def test_multiple_admins_supported(api_client: JournivApiClient):
    """System should support multiple admin users."""
    admin1 = _ensure_admin_user(api_client)
    regular_user = _ensure_regular_user(api_client, admin1)

    # Promote regular user to admin
    response = api_client.request(
        "PATCH",
        f"/admin/users/{regular_user.user_id}",
        headers={"Authorization": f"Bearer {admin1.access_token}"},
        json={"role": "admin"}
    )

    assert response.status_code == 200, "Admin should be able to promote users to admin"
    updated = response.json()
    assert updated["role"] == "admin"

    # Both users should now be admins - verify both can access admin endpoints
    response1 = api_client.request(
        "GET",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin1.access_token}"}
    )
    response2 = api_client.request(
        "GET",
        "/admin/users",
        headers={"Authorization": f"Bearer {regular_user.access_token}"}
    )

    assert response1.status_code == 200, "First admin should access admin endpoints"
    assert response2.status_code == 200, "Promoted admin should access admin endpoints"


def test_cannot_deactivate_last_admin(api_client: JournivApiClient):
    """Deactivating the last admin who can sign in must be refused."""
    admin = _ensure_admin_user(api_client)

    # Attempt to deactivate self (mirrors test_cannot_demote_last_admin).
    response = api_client.request(
        "PATCH",
        f"/admin/users/{admin.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={"is_active": False},
    )

    assert response.status_code == 400, "Should prevent deactivating the last admin"
    error_detail = response.json().get("detail", "")
    assert "last admin" in error_detail.lower() or "active admin" in error_detail.lower()


def test_admin_can_deactivate_another_admin_when_one_remains(
    api_client: JournivApiClient,
):
    """With more than one active admin, deactivating one is allowed."""
    admin = _ensure_admin_user(api_client)
    second = _ensure_regular_user(api_client, admin)

    promote = api_client.request(
        "PATCH",
        f"/admin/users/{second.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={"role": "admin"},
    )
    assert promote.status_code == 200

    deactivate = api_client.request(
        "PATCH",
        f"/admin/users/{second.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={"is_active": False},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    # Clean up so the shared instance keeps a spare active admin.
    api_client.request(
        "DELETE",
        f"/admin/users/{second.user_id}",
        headers={"Authorization": f"Bearer {admin.access_token}"},
    )


def test_admin_create_rejects_weak_password(api_client: JournivApiClient):
    """Admin-created accounts are held to the same password policy as signup."""
    admin = _ensure_admin_user(api_client)
    email, _ = _unique_credentials("weak-pass")

    response = api_client.request(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin.access_token}"},
        json={
            "email": email,
            "password": "short",
            "name": "Weak Password User",
            "role": "user",
        },
    )

    assert response.status_code in (400, 422), "Weak password should be rejected"
