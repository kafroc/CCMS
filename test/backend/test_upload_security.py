"""Unit tests for `app.core.uploads`.

These are pure-function tests — no HTTP. They verify that the helpers
called from every upload endpoint actually block path-traversal and
disallowed extensions.
"""
import os
import pytest
from fastapi import HTTPException

from app.core.uploads import (
    sanitize_filename,
    get_safe_extension,
    validate_size,
    is_within_storage,
    ALLOWED_EXT_TOE_FILE,
    ALLOWED_EXT_ST_REFERENCE,
)
from app.core.config import settings


class TestSanitizeFilename:
    def test_path_segments_stripped(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"
        assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"

    def test_control_chars_replaced(self):
        assert sanitize_filename("hello\x00world.txt") == "hello_world.txt"
        assert sanitize_filename("tab\tname.pdf").startswith("tab")

    def test_empty_becomes_unnamed(self):
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename(None) == "unnamed"
        assert sanitize_filename("   .  ") == "unnamed"

    def test_preserves_unicode(self):
        name = sanitize_filename("安全测试文档.pdf")
        assert name.endswith(".pdf")
        assert "安全" in name

    def test_length_bound(self):
        out = sanitize_filename("a" * 400 + ".pdf")
        assert len(out) <= 255
        assert out.endswith(".pdf")


class TestExtensionWhitelist:
    def test_toe_file_accepts_pdf(self):
        assert get_safe_extension("doc.pdf", ALLOWED_EXT_TOE_FILE) == ".pdf"

    def test_rejects_exe(self):
        with pytest.raises(HTTPException) as exc:
            get_safe_extension("evil.exe", ALLOWED_EXT_TOE_FILE)
        assert exc.value.status_code == 400

    def test_rejects_missing_extension(self):
        with pytest.raises(HTTPException):
            get_safe_extension("Makefile", ALLOWED_EXT_TOE_FILE)

    def test_st_reference_rejects_image(self):
        with pytest.raises(HTTPException):
            get_safe_extension("st.png", ALLOWED_EXT_ST_REFERENCE)


class TestSizeValidation:
    def test_under_limit(self):
        validate_size(100)  # should not raise

    def test_over_limit(self):
        with pytest.raises(HTTPException):
            validate_size(settings.upload_max_bytes + 1)


class TestPathTraversalDefence:
    def test_inside_storage(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "storage_path", str(tmp_path))
        f = tmp_path / "foo" / "bar.pdf"
        f.parent.mkdir(parents=True)
        f.write_text("x")
        assert is_within_storage(str(f)) is True

    def test_outside_storage_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "storage_path", str(tmp_path / "root"))
        (tmp_path / "root").mkdir()
        outside = tmp_path / "leak.pdf"
        outside.write_text("x")
        assert is_within_storage(str(outside)) is False

    def test_traversal_attempt_rejected(self, tmp_path, monkeypatch):
        root = tmp_path / "root"
        root.mkdir()
        monkeypatch.setattr(settings, "storage_path", str(root))
        # A path that LOOKS like it's in root but resolves outside:
        traversal = str(root / ".." / "escape.pdf")
        (tmp_path / "escape.pdf").write_text("x")
        assert is_within_storage(traversal) is False

    def test_empty_rejected(self):
        assert is_within_storage("") is False
        assert is_within_storage(None) is False  # type: ignore[arg-type]
