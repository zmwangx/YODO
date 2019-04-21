import base64
import io
import os
import re
import tempfile
import urllib.parse
import uuid

import pytest


@pytest.fixture(scope="session")
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["STATE_DIRECTORY"] = tmpdir

        import app as yodo

        client = yodo.app.test_client()
        yield client


@pytest.fixture
def image():
    # A small PNG image.
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
    )


def test_intro(client):
    r = client.get()
    assert b"YODO" in r.data


def inspect_create_response(resp):
    assert resp.status_code == 201
    url = resp.data.decode("utf-8").strip()
    url_pattern = re.compile("^http://[^/]+/(?P<uuid>[0-9a-f-]+)$")
    assert url_pattern.match(url)
    identifier = url_pattern.match(url).group("uuid")
    assert uuid.UUID(identifier)
    return f"/{identifier}"


def inspect_read_response(
    resp, expected_data, expected_content_type, expected_filename
):
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == expected_content_type
    if expected_filename:
        assert resp.headers["Content-Disposition"] in (
            f'attachment; filename="{expected_filename}"',
            f"attachment; filename*=UTF-8''{urllib.parse.quote(expected_filename)}",
        )
    else:
        assert "Content-Disposition" not in resp.headers
    assert resp.data == expected_data


def full_test_cycle(client, post_args, expected):
    resource_url = inspect_create_response(client.post("/", **post_args))
    inspect_read_response(
        client.get(resource_url),
        expected["data"],
        expected["content_type"],
        expected["filename"],
    )
    assert client.get(resource_url).status_code == 404


def test_direct_post(client, image):
    full_test_cycle(
        client,
        dict(data=image, content_type="image/png"),
        dict(data=image, content_type="image/png", filename=None),
    )


def test_direct_post_without_content_type(client, image):
    full_test_cycle(
        client,
        dict(data=image),
        dict(data=image, content_type="application/octet-stream", filename=None),
    )


def test_multipart_post(client, image):
    full_test_cycle(
        client,
        dict(data=dict(file=(io.BytesIO(image), "image.png", "image/png"))),
        dict(data=image, content_type="image/png", filename="image.png"),
    )


def test_multipart_post_with_non_ascii_filename(client, image):
    full_test_cycle(
        client,
        dict(data=dict(file=(io.BytesIO(image), "图片.png", "image/png"))),
        dict(data=image, content_type="image/png", filename="图片.png"),
    )


def test_invalid_create(client, image):
    # application/x-www-form-urlencoded
    r = client.post("/", data=dict(file=image))
    assert r.status_code == 400


def test_nonexistent_read(client):
    r = client.get(f"/{uuid.uuid4()}")
    assert r.status_code == 404
