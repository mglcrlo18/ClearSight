"""Static XSS guard for the coder v2 review-queue UI (CWE-79): server text only via textContent / Option."""
import re
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")


def _block(start, end):
    i = JS.index(start)
    return JS[i:JS.index(end, i)]


def test_review_queue_never_uses_innerhtml():
    block = _block("async function loadReviewQueue", "function createTdText")
    assert "innerHTML" not in block and "insertAdjacentHTML" not in block and "outerHTML" not in block
    assert "textContent" in block and "new Option(" in block


def test_review_queue_hooked_into_coding_flow():
    assert re.search(r"data\.coder === 'v2'\)\s*\{\s*loadReviewQueue\(\)", JS)
