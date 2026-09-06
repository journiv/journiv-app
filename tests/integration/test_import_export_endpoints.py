"""
Integration tests for export/import flow-level behaviour.
"""
import io
import uuid
import zipfile

from tests.integration.helpers import (
    UNKNOWN_UUID,
    EndpointCase,
    assert_requires_authentication,
)
from tests.lib import ApiUser, JournivApiClient, make_api_user


def _tiny_zip_with_data() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", "{}")
    return buffer.getvalue()


class TestExportEndpoints:
    """Covers creating export jobs, status polling, and downloads."""

    def test_create_full_export_job(self, api_client: JournivApiClient, api_user: ApiUser):
        response = api_client.request_export(
            api_user.access_token,
            export_type="full",
            include_media=False,
        )
        assert response["export_type"] == "full"
        assert response["status"] in {"queued", "pending", "running"}

    def test_create_journal_export_requires_ids(
        self, api_client: JournivApiClient, api_user: ApiUser, journal_factory
    ):
        missing = api_client.request(
            "POST",
            "/export/",
            token=api_user.access_token,
            json={"export_type": "journal", "include_media": False},
        )
        assert missing.status_code == 400

        journal = journal_factory()
        response = api_client.request_export(
            api_user.access_token,
            export_type="journal",
            journal_ids=[journal["id"]],
        )
        assert response["export_type"] == "journal"

    def test_export_status_and_download_require_auth_and_ownership(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        job = api_client.request_export(api_user.access_token)

        unauthorized_status = api_client.request("GET", f"/export/{job['id']}")
        assert unauthorized_status.status_code == 401

        status = api_client.export_status(api_user.access_token, job["id"])
        assert status["id"] == job["id"]

        other_user = make_api_user(api_client)
        forbidden = api_client.request(
            "GET", f"/export/{job['id']}", token=other_user.access_token
        )
        assert forbidden.status_code == 403

        download = api_client.request("GET", f"/export/{job['id']}/download")
        assert download.status_code == 401

        forbidden_download = api_client.request(
            "GET",
            f"/export/{job['id']}/download",
            token=other_user.access_token,
        )
        assert forbidden_download.status_code in (403, 404)

        pending_download = api_client.request(
            "GET",
            f"/export/{job['id']}/download",
            token=api_user.access_token,
        )
        if pending_download.status_code == 200:
            assert pending_download.headers.get("content-type", "").startswith(
                "application/zip"
            )
            assert pending_download.content
        else:
            assert pending_download.status_code in (400, 404, 500)

    def test_export_status_not_found(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        response = api_client.request(
            "GET",
            f"/export/{uuid.uuid4()}",
            token=api_user.access_token,
        )
        assert response.status_code == 404

    def test_export_history_is_keyset_paginated(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        ids = [
            api_client.request_export(api_user.access_token)["id"]
            for _ in range(3)
        ]

        page1 = api_client.list_exports_page(api_user.access_token, limit=2)
        assert len(page1["items"]) == 2
        assert page1["next_cursor_created_at"] is not None
        assert page1["next_cursor_id"] is not None

        page2 = api_client.list_exports_page(
            api_user.access_token,
            limit=2,
            cursor_created_at=page1["next_cursor_created_at"],
            cursor_id=page1["next_cursor_id"],
        )
        assert len(page2["items"]) == 1
        assert page2["next_cursor_created_at"] is None
        assert page2["next_cursor_id"] is None

        items = page1["items"] + page2["items"]
        assert sorted(item["id"] for item in items) == sorted(ids)
        ordering = [(item["created_at"], item["id"]) for item in items]
        assert ordering == sorted(ordering, reverse=True)

    def test_legacy_export_history_contract_remains_bare_array(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        exports = api_client.request(
            "GET",
            "/export/",
            token=api_user.access_token,
            params={"limit": 1, "offset": 0},
        )
        assert exports.status_code == 200
        assert isinstance(exports.json(), list)

    def test_cancel_export_auth_and_ownership(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        job = api_client.request_export(api_user.access_token)
        unauthorized = api_client.request("POST", f"/export/{job['id']}/cancel")
        assert unauthorized.status_code == 401

        other_user = make_api_user(api_client)
        forbidden = api_client.request(
            "POST",
            f"/export/{job['id']}/cancel",
            token=other_user.access_token,
        )
        assert forbidden.status_code == 403

    def test_cancel_missing_export(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        response = api_client.request(
            "POST",
            f"/export/{uuid.uuid4()}/cancel",
            token=api_user.access_token,
        )
        assert response.status_code == 404

    def test_cancel_finished_export_conflicts(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        job = api_client.request_export(api_user.access_token)

        # The integration stack runs Celery eagerly, so a freshly created export
        # is already in a terminal state by the time the request returns. Assert
        # that precondition explicitly rather than racing a poll loop, so a run
        # against a real broker fails with a clear message instead of a
        # confusing 200-vs-409.
        status_body = api_client.export_status(api_user.access_token, job["id"])
        assert status_body["status"] not in {"pending", "running"}, (
            f"expected the eager worker to finish the export, got "
            f"{status_body['status']!r}"
        )

        response = api_client.request(
            "POST",
            f"/export/{job['id']}/cancel",
            token=api_user.access_token,
        )
        assert response.status_code == 409

    def test_export_requires_auth(self, api_client: JournivApiClient):
        assert_requires_authentication(
            api_client,
            [
                EndpointCase(
                    "POST",
                    "/export/",
                    json={"export_type": "full", "include_media": False},
                ),
                EndpointCase("GET", "/export/", params={"format": "page"}),
                EndpointCase("POST", f"/export/{UNKNOWN_UUID}/cancel"),
            ],
        )


class TestImportEndpoints:
    """Covers import job upload/validation and status polling."""

    def test_upload_import_job(self, api_client: JournivApiClient, api_user: ApiUser):
        response = api_client.upload_import(
            api_user.access_token,
            file_bytes=_tiny_zip_with_data(),
        )
        assert response.status_code in (202, 400, 500)

    def test_import_job_lifecycle(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        upload = api_client.upload_import(
            api_user.access_token,
            file_bytes=_tiny_zip_with_data(),
        )
        assert upload.status_code == 202
        job = upload.json()

        status = api_client.import_status(api_user.access_token, job["id"])
        assert status["id"] == job["id"]

        listing = api_client.list_imports(api_user.access_token)
        assert any(item["id"] == job["id"] for item in listing)

        other_user = make_api_user(api_client)
        forbidden = api_client.request(
            "GET", f"/import/{job['id']}", token=other_user.access_token
        )
        assert forbidden.status_code == 403

        api_client.delete_import(api_user.access_token, job["id"])
        missing = api_client.request(
            "GET", f"/import/{job['id']}", token=api_user.access_token
        )
        assert missing.status_code == 404

    def test_import_invalid_file_type(self, api_client: JournivApiClient, api_user: ApiUser):
        response = api_client.request(
            "POST",
            "/import/upload",
            token=api_user.access_token,
            files={"file": ("not.zip", io.BytesIO(b"nope"), "text/plain")},
            data={"source_type": "journiv"},
        )
        assert response.status_code == 400

    def test_import_status_not_found(self, api_client: JournivApiClient, api_user: ApiUser):
        response = api_client.request(
            "GET",
            f"/import/{uuid.uuid4()}",
            token=api_user.access_token,
        )
        assert response.status_code == 404

    def test_import_list_empty_and_delete_missing(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        listing = api_client.list_imports(api_user.access_token)
        assert isinstance(listing, list)

        response = api_client.request(
            "DELETE",
            f"/import/{uuid.uuid4()}",
            token=api_user.access_token,
        )
        assert response.status_code in (404, 409)

    def test_import_history_is_keyset_paginated(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        ids = [
            api_client.upload_import(
                api_user.access_token,
                file_bytes=_tiny_zip_with_data(),
                expected=(202,),
            ).json()["id"]
            for _ in range(3)
        ]

        page1 = api_client.list_imports_page(api_user.access_token, limit=2)
        page2 = api_client.list_imports_page(
            api_user.access_token,
            limit=2,
            cursor_created_at=page1["next_cursor_created_at"],
            cursor_id=page1["next_cursor_id"],
        )

        assert len(page1["items"]) == 2
        assert page1["next_cursor_id"] is not None
        assert len(page2["items"]) == 1
        assert page2["next_cursor_created_at"] is None
        assert page2["next_cursor_id"] is None
        items = page1["items"] + page2["items"]
        assert sorted(item["id"] for item in items) == sorted(ids)
        ordering = [(item["created_at"], item["id"]) for item in items]
        assert ordering == sorted(ordering, reverse=True)

    def test_legacy_import_history_contract_remains_bare_array(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        imports = api_client.request(
            "GET",
            "/import/",
            token=api_user.access_token,
            params={"limit": 1, "offset": 0},
        )
        assert imports.status_code == 200
        assert isinstance(imports.json(), list)

    def test_cancel_missing_import(
        self, api_client: JournivApiClient, api_user: ApiUser
    ):
        response = api_client.request(
            "POST",
            f"/import/{uuid.uuid4()}/cancel",
            token=api_user.access_token,
        )
        assert response.status_code == 404

    def test_import_requires_authentication(self, api_client: JournivApiClient):
        assert_requires_authentication(
            api_client,
            [
                EndpointCase(
                    "POST",
                    "/import/upload",
                    files={
                        "file": ("export.zip", io.BytesIO(b"zip"), "application/zip")
                    },
                    data={"source_type": "journiv"},
                ),
                EndpointCase("GET", "/import/"),
                EndpointCase("GET", f"/import/{UNKNOWN_UUID}"),
                EndpointCase("POST", f"/import/{UNKNOWN_UUID}/cancel"),
            ],
        )
