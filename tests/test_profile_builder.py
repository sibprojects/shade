"""Create a call profile from a CV and a job description."""

import threading
import zipfile

import pytest

from shade.llm.base import ProviderError
from shade.models import Usage
from shade.profile_builder import (
    PROFILE_RULES,
    build_profile_request,
    clean_profile,
    generate_profile,
    profile_path,
    read_document,
)


class Fake:
    model = "fake"
    supports_images = True

    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.last_usage = Usage()
        self.calls = []

    def stream_answer(self, system, user_text, image_png, cancel):
        self.calls.append((system, user_text))
        for c in self.chunks:
            if cancel.is_set():
                return
            yield c
        if self.error:
            raise self.error


def test_request_contains_cv_job_and_notes():
    text = build_profile_request("CV: PHP 8 dev", "Job: Senior PHP", "Two interviewers, live coding.")
    assert "CV: PHP 8 dev" in text
    assert "Job: Senior PHP" in text
    assert "Two interviewers, live coding." in text


def test_request_without_job_or_notes_says_so():
    text = build_profile_request("CV text", "", "")
    assert "CV text" in text
    assert "No job description" in text


def test_rules_ask_for_the_sections_shade_uses():
    for section in ("## About me", "## Experience", "## This call", "## How to answer", "## Gaps"):
        assert section in PROFILE_RULES
    assert "Terms:" in PROFILE_RULES  # first line of This call goes to the speech model


def test_generate_streams_and_cleans():
    deltas = []
    p = Fake(["```markdown\n# PHP", " interview\n\n## About me\n- x\n```"])
    out = generate_profile(p, "cv", "job", "", threading.Event(), on_delta=deltas.append)
    assert out == "# PHP interview\n\n## About me\n- x\n"
    assert "".join(deltas).startswith("```markdown")
    assert p.calls[0][0] == PROFILE_RULES


def test_generate_needs_a_cv():
    with pytest.raises(ValueError):
        generate_profile(Fake([]), "  ", "job", "", threading.Event())


def test_generate_passes_provider_errors():
    with pytest.raises(ProviderError):
        generate_profile(Fake(["# x"], error=ProviderError("down")), "cv", "", "", threading.Event())


def test_clean_profile_keeps_plain_markdown():
    assert clean_profile("# Title\n\n- a\n") == "# Title\n\n- a\n"
    assert clean_profile("Here is it:\n\n# Title\n- a") == "# Title\n- a\n"


def test_read_document_txt_utf8_and_cp1251(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("Senior — PHP", encoding="utf-8")
    b = tmp_path / "b,txt"
    b.write_bytes("Опыт работы".encode("cp1251"))
    assert read_document(a) == "Senior — PHP"
    assert read_document(b) == "Опыт работы"


def test_read_document_docx(tmp_path):
    path = tmp_path / "cv.docx"
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        "<w:p><w:r><w:t>John Doe</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>PHP </w:t></w:r><w:r><w:t>developer</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    assert read_document(path) == "John Doe\nPHP developer"


def test_profile_path_is_new_file(tmp_path):
    assert profile_path(tmp_path, "PHP Backend / Acme") == tmp_path / "php-backend-acme.md"
    (tmp_path / "php-backend-acme.md").write_text("x")
    assert profile_path(tmp_path, "PHP Backend / Acme") == tmp_path / "php-backend-acme-2.md"


def test_dialog_generates_and_saves(qtbot, tmp_path):
    from shade.ui.profile_dialog import ProfileDialog

    p = Fake(["# PHP interview\n\n## About me\n- PHP\n"])
    d = ProfileDialog(lambda: p, tmp_path)
    qtbot.addWidget(d)
    d.name.setText("PHP interview")
    d.cv.setPlainText("10 years PHP")
    d.job.setPlainText("Senior PHP engineer")
    d.generate()
    qtbot.waitUntil(lambda: d.save_button.isEnabled(), timeout=5000)
    assert "## About me" in d.result.toPlainText()
    saved = d.save()
    assert saved == tmp_path / "php-interview.md"
    assert saved.read_text(encoding="utf-8").startswith("# PHP interview")


def test_dialog_shows_errors(qtbot, tmp_path):
    from shade.ui.profile_dialog import ProfileDialog

    d = ProfileDialog(lambda: Fake([], error=ProviderError("Claude Code: usage limit.")), tmp_path)
    qtbot.addWidget(d)
    d.cv.setPlainText("cv")
    d.generate()
    qtbot.waitUntil(lambda: "usage limit" in d.status.text(), timeout=5000)
    assert not d.save_button.isEnabled()
