"""Tests for the /convert-markdown-to-docx endpoint with .md and .zip support."""
import io
import sys
import zipfile
import base64
from pathlib import Path

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def test_md_upload(client):
    resp = client.post(
        "/convert-markdown-to-docx",
        files={"file": ("test.md", b"# Hello\nSome text", "text/markdown")},
    )
    assert resp.status_code == 200
    assert len(resp.content) > 0


def test_zip_upload_with_images(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("doc.md", "# With image\n![logo](images/logo.png)\n")
        z.writestr("images/logo.png", TINY_PNG)
    buf.seek(0)
    resp = client.post(
        "/convert-markdown-to-docx",
        files={"file": ("docs.zip", buf.read(), "application/zip")},
    )
    assert resp.status_code == 200
    assert len(resp.content) > 0


def test_bad_extension_rejected(client):
    resp = client.post(
        "/convert-markdown-to-docx",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_zip_without_markdown_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "no markdown here")
    buf.seek(0)
    resp = client.post(
        "/convert-markdown-to-docx",
        files={"file": ("empty.zip", buf.read(), "application/zip")},
    )
    assert resp.status_code == 400
