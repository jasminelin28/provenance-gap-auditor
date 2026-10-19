"""Capture the screenshots used in report.html and slides.html.

Drives the real running app with a headless browser, so every image in the
report is a genuine run rather than a mock-up.

Usage (with the app already running on port 8050):
    python tools/capture_screenshots.py

Playwright is a development-only dependency and is deliberately not listed in
requirements.txt: the app itself never needs it.
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

repo_root = Path(__file__).resolve().parent.parent
output_directory = repo_root / "assets" / "screenshots"
base_url = "http://127.0.0.1:8050"

# Wide enough for the two-column layout, at 2x for a crisp printed report.
viewport = {"width": 1320, "height": 1000}
scale_factor = 2
audit_timeout_ms = 180_000


def wait_for_results(page) -> None:
    """Block until the audit has rendered, not merely until the click lands."""
    page.wait_for_function(
        """() => {
            const r = document.getElementById('results');
            return r && r.innerText.includes('SUMMARY');
        }""",
        timeout=audit_timeout_ms,
    )
    # Let the map finish drawing before we photograph it.
    page.wait_for_timeout(2500)


def run_sample(page, text: str) -> None:
    page.fill("#record_input", text)
    page.click("#audit_button")
    # On a second run the previous results are still on screen, so waiting on
    # the text alone would photograph the old audit. Wait for the loading
    # painter to appear and then go away.
    try:
        page.wait_for_selector(".painter_scene", state="attached", timeout=15_000)
        page.wait_for_selector(".painter_scene", state="detached",
                               timeout=audit_timeout_ms)
    except Exception:
        pass
    wait_for_results(page)
    page.wait_for_timeout(1200)


def shoot(page, name: str, selector: str | None = None, full: bool = False) -> None:
    path = output_directory / f"{name}.png"
    if selector:
        page.locator(selector).first.screenshot(path=str(path))
    else:
        page.screenshot(path=str(path), full_page=full)
    size_kb = path.stat().st_size // 1024
    print(f"  {path.name:34} {size_kb:5} KB")


def section_with(page, heading: str) -> str:
    """A CSS selector for the section whose heading matches.

    The headings are uppercased by CSS, so the text in the DOM is the
    title-case string passed to section(), not what the screen shows.
    """
    return f"section:has(h2:text-is('{heading}'))"


def main() -> int:
    output_directory.mkdir(parents=True, exist_ok=True)
    samples = repo_root / "samples"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=viewport,
                                device_scale_factor=scale_factor)
        page.goto(base_url, wait_until="networkidle")

        # ---- 1. the headline case: the Klimt -------------------------------
        print("Klimt (high risk):")
        run_sample(page, (samples / "klimt_adele.txt").read_text(encoding="utf-8"))

        page.evaluate("window.scrollTo(0, 0)")
        shoot(page, "01_overview")
        shoot(page, "02_summary", section_with(page, "Summary"))
        shoot(page, "03_work_facts", section_with(page, "The work"))
        shoot(page, "04_map", section_with(page, "Where the work travelled"))

        # Open the flagged row so the inline detail is visible.
        page.evaluate(
            "document.querySelectorAll('.chain_row_details')[0].open = true")
        page.wait_for_timeout(400)
        shoot(page, "05_chain_expanded", section_with(page, "Ownership chain"))

        shoot(page, "06_gaps", section_with(page, "Gaps"))
        shoot(page, "07_score_breakdown",
              section_with(page, "How the score was reached"))
        shoot(page, "08_full_page", full=True)

        # ---- 2. the safety case: prompt injection --------------------------
        print("Injection attempt (safety evidence):")
        run_sample(page,
                   (samples / "injection_subtle.txt").read_text(encoding="utf-8"))
        page.evaluate("window.scrollTo(0, 0)")
        shoot(page, "09_injection_summary", section_with(page, "Summary"))
        shoot(page, "10_injection_notes",
              section_with(page, "Notes on this run"))

        # ---- 3. the control: a post-war work -------------------------------
        print("Post-war control (no false positive):")
        run_sample(page,
                   (samples / "clean_contemporary.txt").read_text(encoding="utf-8"))
        page.evaluate("window.scrollTo(0, 0)")
        shoot(page, "11_control_summary", section_with(page, "Summary"))

        browser.close()

    print(f"\nWrote screenshots to {output_directory}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
