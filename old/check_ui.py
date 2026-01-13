"""
Playwright script to check the UI and console logs for issues.
"""

import asyncio
from playwright.async_api import async_playwright


async def check_ui():
    """Check UI pages and collect console logs."""

    console_logs = []
    errors = []
    network_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Collect console messages
        def handle_console(msg):
            log_entry = f"[{msg.type}] {msg.text}"
            console_logs.append(log_entry)
            if msg.type == "error":
                errors.append(log_entry)

        page.on("console", handle_console)

        # Collect page errors
        def handle_page_error(error):
            errors.append(f"[PAGE ERROR] {error}")

        page.on("pageerror", handle_page_error)

        # Collect network failures
        def handle_request_failed(request):
            network_errors.append(f"[NETWORK] Failed: {request.url} - {request.failure}")

        page.on("requestfailed", handle_request_failed)

        print("=" * 60)
        print("CHECKING GOOD-SIGNAL UI")
        print("=" * 60)

        # Check each page
        pages_to_check = [
            ("http://localhost:5175/", "Home/Backtest Page"),
            ("http://localhost:5175/backtest", "Backtest Page"),
            ("http://localhost:5175/live", "Live Trading Page"),
            ("http://localhost:5175/positions", "Positions Page"),
            ("http://localhost:5175/settings", "Settings Page"),
        ]

        for url, name in pages_to_check:
            print(f"\n--- Checking: {name} ({url}) ---")
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=15000)

                # Wait a bit for React to render
                await page.wait_for_timeout(2000)

                # Get page title
                title = await page.title()
                print(f"  Title: {title}")
                print(f"  Status: {response.status if response else 'N/A'}")

                # Check if page has main content
                body_text = await page.inner_text("body")
                if len(body_text.strip()) < 50:
                    print(f"  WARNING: Page appears to have minimal content")
                else:
                    print(f"  Content: OK ({len(body_text)} chars)")

                # Take screenshot
                screenshot_name = f"screenshot_{name.lower().replace(' ', '_').replace('/', '_')}.png"
                await page.screenshot(path=f"data/{screenshot_name}")
                print(f"  Screenshot saved: data/{screenshot_name}")

            except Exception as e:
                print(f"  ERROR loading page: {e}")
                errors.append(f"[LOAD ERROR] {name}: {e}")

        # Check API health
        print("\n--- Checking Backend API ---")
        try:
            api_response = await page.goto("http://localhost:8000/api/health", timeout=5000)
            if api_response:
                print(f"  Health endpoint: {api_response.status}")
                health_text = await page.inner_text("body")
                print(f"  Response: {health_text[:200]}")
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"[API ERROR] Health check: {e}")

        await browser.close()

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\nTotal console logs: {len(console_logs)}")
    print(f"Console errors: {len([l for l in console_logs if l.startswith('[error]')])}")
    print(f"Network errors: {len(network_errors)}")
    print(f"Page errors: {len(errors)}")

    if errors:
        print("\n--- ERRORS FOUND ---")
        for error in errors:
            print(f"  {error}")

    if network_errors:
        print("\n--- NETWORK ERRORS ---")
        for error in network_errors:
            print(f"  {error}")

    # Print console errors specifically
    console_errors = [l for l in console_logs if l.startswith("[error]")]
    if console_errors:
        print("\n--- CONSOLE ERRORS ---")
        for error in console_errors:
            print(f"  {error}")

    # Print warnings
    console_warnings = [l for l in console_logs if l.startswith("[warning]")]
    if console_warnings:
        print("\n--- CONSOLE WARNINGS ---")
        for warning in console_warnings[:10]:  # Limit to first 10
            print(f"  {warning}")
        if len(console_warnings) > 10:
            print(f"  ... and {len(console_warnings) - 10} more warnings")

    print("\n" + "=" * 60)
    if not errors and not network_errors and not console_errors:
        print("All checks passed!")
    else:
        print(f"Found {len(errors) + len(network_errors) + len(console_errors)} issues")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(check_ui())
