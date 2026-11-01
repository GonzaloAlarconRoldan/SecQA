"""Visual evidence: headless-browser screenshots of what a vulnerability looks like in the UI.

`secqa capture` opens a URL (after the scope check), optionally highlights the element that proves
the issue, masks sensitive data, stamps an evidence banner (URL · UTC time · run) and saves a PNG
that can be attached to a finding. Requires the `capture` extra: pip install "secqa[capture]".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Masks values that commonly leak: emails, JWTs, bcrypt/MD5/SHA hashes, card-like numbers, API keys.
DEFAULT_SENSITIVE_PATTERNS = (
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}",
    r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b",
    r"\b(?:\d[ -]?){13,16}\b",
    r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}\b|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b",
)

_MASK_JS = r"""
(patterns) => {
  const res = patterns.map((p) => new RegExp(p, 'g'));
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n, count = 0;
  while ((n = walker.nextNode())) {
    let t = n.nodeValue;
    for (const re of res) {
      t = t.replace(re, (m) => {
        count++;
        return m.slice(0, 2) + '█'.repeat(Math.max(4, Math.min(m.length - 2, 12)));
      });
    }
    if (t !== n.nodeValue) n.nodeValue = t;
  }
  for (const el of document.querySelectorAll('input')) {
    for (const re of res) { if (re.test(el.value)) { el.value = '████████'; count++; } re.lastIndex = 0; }
  }
  return count;
}
"""

_HIGHLIGHT_JS = r"""
(selector) => {
  const els = Array.from(document.querySelectorAll(selector));
  els.forEach((el, i) => {
    el.style.outline = '4px solid #e11d48';
    el.style.outlineOffset = '3px';
    if (i === 0) el.scrollIntoView({ block: 'center' });
  });
  return els.length;
}
"""

_BANNER_JS = r"""
(text) => {
  const b = document.createElement('div');
  b.textContent = text;
  b.setAttribute('data-secqa-banner', '1');
  Object.assign(b.style, {
    position: 'fixed', left: '0', right: '0', bottom: '0', zIndex: '2147483647',
    background: 'rgba(15,23,42,0.92)', color: '#f8fafc', font: '12px/1.4 ui-monospace, Menlo, monospace',
    padding: '6px 12px', borderTop: '3px solid #e11d48', whiteSpace: 'nowrap', overflow: 'hidden',
    textOverflow: 'ellipsis',
  });
  document.body.appendChild(b);
}
"""


class CaptureError(Exception):
    pass


@dataclass
class CaptureOptions:
    url: str
    output: Path
    highlight: str | None = None
    mask_selectors: list[str] = field(default_factory=list)
    mask_patterns: list[str] = field(default_factory=list)
    mask_defaults: bool = True
    headers: dict[str, str] = field(default_factory=dict)
    storage_state: Path | None = None
    wait_for: str | None = None
    # UI steps before the screenshot, e.g. type a payload into a login form and submit it
    fill: list[tuple[str, str]] = field(default_factory=list)
    click: str | None = None
    full_page: bool = False
    viewport: tuple[int, int] = (1280, 720)
    banner: str | None = ""  # "" → default banner; None → no banner
    timeout_ms: int = 30000


@dataclass
class CaptureResult:
    output: Path
    final_url: str
    status: int | None
    highlighted: int
    masked: int


def _launch(p):
    # Prefer the user's installed Chrome (no download); fall back to Playwright's bundled Chromium.
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:  # any launch failure → try the next option
        try:
            return p.chromium.launch()
        except Exception as exc:
            raise CaptureError("no browser available — install Chrome, or run: "
                               "python -m playwright install chromium") from exc


def capture(opts: CaptureOptions) -> CaptureResult:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise CaptureError('screenshots need Playwright — pip install "secqa[capture]" '
                           "(or: secqa doctor --install --only playwright)") from exc

    for pattern in opts.mask_patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise CaptureError(f"invalid --mask-text regex {pattern!r}: {exc}") from exc
    patterns = list(opts.mask_patterns) + (list(DEFAULT_SENSITIVE_PATTERNS) if opts.mask_defaults else [])

    opts.output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            context = browser.new_context(
                viewport={"width": opts.viewport[0], "height": opts.viewport[1]},
                extra_http_headers=opts.headers or None,
                storage_state=str(opts.storage_state) if opts.storage_state else None,
                ignore_https_errors=True,  # local/self-signed targets only (scope-checked by the caller)
            )
            page = context.new_page()
            try:
                response = page.goto(opts.url, wait_until="networkidle", timeout=opts.timeout_ms)
                for selector, value in opts.fill:
                    page.fill(selector, value, timeout=opts.timeout_ms)
                if opts.click:
                    with page.expect_navigation(wait_until="networkidle", timeout=opts.timeout_ms) as nav:
                        page.click(opts.click, timeout=opts.timeout_ms)
                    response = nav.value or response
                if opts.wait_for:
                    page.wait_for_selector(opts.wait_for, timeout=opts.timeout_ms)
            except PlaywrightError as exc:
                raise CaptureError(f"could not load {opts.url}: {exc.message.splitlines()[0]}") from exc

            highlighted = page.evaluate(_HIGHLIGHT_JS, opts.highlight) if opts.highlight else 0
            if opts.highlight and not highlighted:
                raise CaptureError(f"--highlight selector matched nothing: {opts.highlight}")
            masked = page.evaluate(_MASK_JS, patterns) if patterns else 0
            if opts.banner is not None:
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                text = " · ".join(filter(None, ["SecQA evidence", page.url, stamp, opts.banner]))
                page.evaluate(_BANNER_JS, text)
            page.screenshot(
                path=str(opts.output),
                full_page=opts.full_page,
                mask=[page.locator(s) for s in opts.mask_selectors],
                mask_color="#0f172a",
            )
            return CaptureResult(opts.output, page.url, response.status if response else None, highlighted, masked)
        finally:
            browser.close()
