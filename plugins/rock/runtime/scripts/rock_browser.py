"""Rock RMS browser automation via Playwright.

Uses the same ROCK_USERNAME/ROCK_PASSWORD credentials as the API client.
Authenticates via the Rock login page, then provides utilities for
page verification, screenshots, and form interaction.

Usage:
  uv run scripts/rock_browser.py login          # verify login works
  uv run scripts/rock_browser.py screenshot <url-path> [output.png]
  uv run scripts/rock_browser.py check-element <url-path> <selector>
  uv run scripts/rock_browser.py verify-page <page-id>
"""

import argparse
import sys
from pathlib import Path

import rock_paths

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

from rock_client import get_credentials
from rock_log import get_logger

log = get_logger("rock.browser")

SCREENSHOTS_DIR = rock_paths.SCREENSHOTS


class RockBrowser:
    def __init__(self, headless=True):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        self.page = self._context.new_page()
        self.base_url, self._username, self._password = get_credentials()
        self._logged_in = False

    def login(self):
        if self._logged_in:
            return True

        log.info("browser login user=%s", self._username)
        self.page.goto(f"{self.base_url}/Login", wait_until="networkidle", timeout=30000)

        # Rock v17 login form uses ASP.NET WebForms with dynamic control IDs.
        # The login button is an <a> that triggers a postback, then redirects.
        try:
            self.page.fill('input[id$="tbUserName"]', self._username, timeout=10000)
            self.page.fill('input[id$="tbPassword"]', self._password, timeout=5000)
            with self.page.expect_navigation(wait_until="networkidle", timeout=30000):
                self.page.click('a[id$="btnLogin"]', timeout=5000)
        except PwTimeout:
            log.error("browser login timed out -- login form not found or submission hung")
            return False

        # Check if we landed on a logged-in page (not still at /Login)
        current_url = self.page.url
        if "/Login" in current_url or "/login" in current_url:
            error = self.page.query_selector('.alert-danger, .validation-summary-errors, .text-danger')
            err_text = error.inner_text() if error else "unknown"
            log.error("browser login failed: %s", err_text)
            return False

        self._logged_in = True
        log.info("browser login ok url=%s", current_url)
        return True

    def goto(self, path):
        if not self._logged_in:
            self.login()
        url = f"{self.base_url}/{path.lstrip('/')}"
        log.info("browser goto %s", path)
        self.page.goto(url, wait_until="networkidle", timeout=30000)
        return self.page

    def screenshot(self, path, output=None):
        self.goto(path)
        if output is None:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            slug = path.strip("/").replace("/", "-").replace("?", "_") or "home"
            output = str(SCREENSHOTS_DIR / f"{slug}.png")
        self.page.screenshot(path=output, full_page=True)
        log.info("screenshot saved %s", output)
        return output

    def check_element(self, path, selector, timeout=10000):
        self.goto(path)
        try:
            el = self.page.wait_for_selector(selector, timeout=timeout)
            visible = el.is_visible() if el else False
            bbox = el.bounding_box() if el else None
            log.info("check_element path=%s selector=%s visible=%s", path, selector, visible)
            return {"found": True, "visible": visible, "bbox": bbox}
        except PwTimeout:
            log.info("check_element path=%s selector=%s not_found", path, selector)
            return {"found": False, "visible": False, "bbox": None}

    def check_elements(self, path, selectors):
        self.goto(path)
        results = {}
        for selector in selectors:
            try:
                el = self.page.wait_for_selector(selector, timeout=5000)
                visible = el.is_visible() if el else False
                results[selector] = {"found": True, "visible": visible}
            except PwTimeout:
                results[selector] = {"found": False, "visible": False}
        return results

    def get_text(self, path, selector, timeout=10000):
        self.goto(path)
        try:
            el = self.page.wait_for_selector(selector, timeout=timeout)
            text = el.inner_text() if el else ""
            return text
        except PwTimeout:
            return None

    def get_block_content(self, page_id, zone="Main"):
        path = f"page/{page_id}"
        self.goto(path)
        blocks = self.page.query_selector_all(f'.zone-{zone.lower()} .block-instance, .block-content')
        results = []
        for b in blocks:
            results.append({
                "html": b.inner_html()[:500],
                "text": b.inner_text()[:300],
                "visible": b.is_visible(),
            })
        return results

    def fill_form(self, path, fields, submit_selector=None):
        self.goto(path)
        for selector, value in fields.items():
            try:
                el = self.page.wait_for_selector(selector, timeout=5000)
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    self.page.select_option(selector, label=value)
                elif tag == "input":
                    input_type = el.get_attribute("type") or "text"
                    if input_type in ("checkbox", "radio"):
                        if value:
                            el.check()
                        else:
                            el.uncheck()
                    else:
                        self.page.fill(selector, value)
                else:
                    self.page.fill(selector, value)
                log.info("fill_form %s=%s", selector, value[:50] if isinstance(value, str) else value)
            except PwTimeout:
                log.error("fill_form field not found: %s", selector)
                return False
        if submit_selector:
            self.page.click(submit_selector)
            self.page.wait_for_load_state("networkidle", timeout=15000)
        return True

    def verify_page(self, page_id):
        path = f"page/{page_id}"
        self.goto(path)
        title = self.page.title()
        status = self.page.evaluate("() => document.readyState")
        errors = self.page.query_selector_all('.alert-danger, .alert-warning, .error')
        error_texts = [e.inner_text() for e in errors]

        # Check for Rock error panel
        rock_error = self.page.query_selector('.exception-detail, .rock-error')
        if rock_error:
            error_texts.append(rock_error.inner_text()[:300])

        result = {
            "page_id": page_id,
            "title": title,
            "url": self.page.url,
            "ready_state": status,
            "errors": error_texts,
            "ok": len(error_texts) == 0,
        }
        log.info("verify_page id=%d ok=%s errors=%d", page_id, result["ok"], len(error_texts))
        return result

    def close(self):
        self._context.close()
        self._browser.close()
        self._pw.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def cmd_login(args):
    with RockBrowser(headless=not args.headed) as browser:
        ok = browser.login()
        if ok:
            print(f"Login successful. URL: {browser.page.url}")
            print(f"Title: {browser.page.title()}")
        else:
            print("Login failed.")
            sys.exit(1)


def cmd_screenshot(args):
    with RockBrowser(headless=not args.headed) as browser:
        output = browser.screenshot(args.path, args.output)
        print(f"Screenshot saved: {output}")


def cmd_check_element(args):
    with RockBrowser(headless=not args.headed) as browser:
        result = browser.check_element(args.path, args.selector)
        if result["found"]:
            vis = "visible" if result["visible"] else "hidden"
            print(f"Element found ({vis}): {args.selector}")
            if result["bbox"]:
                b = result["bbox"]
                print(f"  Position: {b['x']:.0f},{b['y']:.0f} Size: {b['width']:.0f}x{b['height']:.0f}")
        else:
            print(f"Element NOT found: {args.selector}")
            sys.exit(1)


def cmd_verify_page(args):
    with RockBrowser(headless=not args.headed) as browser:
        result = browser.verify_page(args.page_id)
        print(f"Page {args.page_id}: {'OK' if result['ok'] else 'ERRORS'}")
        print(f"  Title: {result['title']}")
        print(f"  URL: {result['url']}")
        if result["errors"]:
            print(f"  Errors ({len(result['errors'])}):")
            for e in result["errors"]:
                print(f"    {e[:200]}")


def main():
    parser = argparse.ArgumentParser(description="Rock RMS browser automation")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("login", help="Verify browser login works")

    p_ss = subparsers.add_parser("screenshot", help="Take a screenshot")
    p_ss.add_argument("path", help="URL path (e.g. /page/123)")
    p_ss.add_argument("output", nargs="?", help="Output file path")

    p_ce = subparsers.add_parser("check-element", help="Check if element exists")
    p_ce.add_argument("path", help="URL path")
    p_ce.add_argument("selector", help="CSS selector")

    p_vp = subparsers.add_parser("verify-page", help="Verify a page loads without errors")
    p_vp.add_argument("page_id", type=int, help="Rock page ID")

    parsed = parser.parse_args()
    if parsed.command == "login":
        cmd_login(parsed)
    elif parsed.command == "screenshot":
        cmd_screenshot(parsed)
    elif parsed.command == "check-element":
        cmd_check_element(parsed)
    elif parsed.command == "verify-page":
        cmd_verify_page(parsed)


if __name__ == "__main__":
    main()
