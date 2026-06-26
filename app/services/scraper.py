# app/services/scraper.py
import httpx
from playwright.async_api import async_playwright

async def fetch_static(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()
        return response.text

async def fetch_dynamic(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            # Set standard viewport and headers to look realistic
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()
            return content
        finally:
            await browser.close()

async def fetch_page(url: str, requires_js: bool = False) -> str:
    if requires_js:
        return await fetch_dynamic(url)
    else:
        try:
            return await fetch_static(url)
        except Exception:
            # Fallback to dynamic if static fails
            return await fetch_dynamic(url)
