import asyncio
from typing import List, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from base import BaseScraper, ScrapedListing


class HousingScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(headless=headless)
        self.source_name = "Housing"

        # Keep selectors pragmatic, not pretty
        self.SELECTORS = {
            "search_input": [
                'input[placeholder*="Search"]',
                'input[name="q"]',
                'input[type="text"]',
            ],
            "listing_card": [
                'article[data-q="listing-card"]',
                'div[data-q="listing-card"]',
                'article',  # dirty fallback (important)
            ],
            "price": [
                '[data-q="price"]',
                'span[class*="price"]',
                'div[class*="price"]',
            ],
            "title": [
                '[data-q="title"]',
                'h2',
            ],
            "image": [
                'img[data-q="listing-image"]',
                'img[data-src]',
                'img[src]',
            ],
        }

    # ---------------- helpers ----------------

    async def _find_first(self, page, selectors, timeout=8000):
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=timeout)
                if el:
                    return el
            except PlaywrightTimeout:
                continue
        return None

    async def _search_location(self, page, location: str) -> bool:
        print(f"[Housing] 🔍 Searching for: {location}")

        search = await self._find_first(page, self.SELECTORS["search_input"])
        if not search:
            print("[Housing] ❌ Search box not found")
            return False

        await search.click()
        await search.fill("")
        await search.type(location, delay=120)

        # let autocomplete attach
        await page.wait_for_timeout(1000)

        # keyboard selection is most stable
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("Enter")

        return True

    async def _wait_for_redirect(self, page, start_url: str) -> bool:
        try:
            await page.wait_for_url(lambda u: u != start_url, timeout=30000)
            print(f"[DEBUG] URL changed to: {page.url}")
            return True
        except PlaywrightTimeout:
            print("[Housing] ❌ URL never changed after search")
            return False

    async def _scroll(self, page, rounds=3):
        for _ in range(rounds):
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)

    async def _extract_card(self, card) -> Optional[ScrapedListing]:
        try:
            raw_text = await card.inner_text()

            link = await card.query_selector("a")
            href = await link.get_attribute("href") if link else None
            url = f"https://housing.com{href}" if href and href.startswith("/") else href
            raw_id = href.split("/")[-1] if href else "unknown"

            price = "0"
            for sel in self.SELECTORS["price"]:
                el = await card.query_selector(sel)
                if el:
                    price = (await el.inner_text()).strip()
                    break

            title = "Unknown Property"
            for sel in self.SELECTORS["title"]:
                el = await card.query_selector(sel)
                if el:
                    title = (await el.inner_text()).strip()
                    break

            image_url = None
            for sel in self.SELECTORS["image"]:
                img = await card.query_selector(sel)
                if img:
                    image_url = await img.get_attribute("src") or await img.get_attribute("data-src")
                    break

            return ScrapedListing(
                id=self._make_id(raw_id),
                source=self.source_name,
                url=url or "",
                raw_text=raw_text,
                price_str=price,
                title=title,
                location="",
                image_url=image_url,
            )

        except Exception:
            return None

    # ---------------- main ----------------

    async def scrape(
        self,
        location: str,
        budget_min: int,
        budget_max: int,
        **kwargs,
    ) -> List[ScrapedListing]:

        budget_min, budget_max = self._validate_budget(budget_min, budget_max)
        listings: List[ScrapedListing] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-IN",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            page = await context.new_page()
            start_url = "https://housing.com/in/rent"

            try:
                print("[Housing] 🏠 Opening rent page")
                await page.goto(start_url, timeout=60000, wait_until="domcontentloaded")

                if not await self._search_location(page, location):
                    self.log_failure(location, "rent")
                    return []

                # 🔑 critical step
                if not await self._wait_for_redirect(page, start_url):
                    self.log_failure(location, "rent")
                    return []

                # 🔑 force hydration
                await page.goto(page.url, wait_until="domcontentloaded")

                # wait for ANY listing card
                cards = []
                for sel in self.SELECTORS["listing_card"]:
                    try:
                        await page.wait_for_selector(sel, timeout=15000)
                        cards = await page.query_selector_all(sel)
                        if cards:
                            break
                    except PlaywrightTimeout:
                        continue

                if not cards:
                    print(f"[Housing] ⚠️ No listings available for {location}")
                    self.log_failure(location, "rent")
                    return []

                # scroll AFTER cards exist
                await self._scroll(page, rounds=3)

                # re-query after scroll
                cards = []
                for sel in self.SELECTORS["listing_card"]:
                    cards = await page.query_selector_all(sel)
                    if cards:
                        break

                for card in cards[:25]:
                    listing = await self._extract_card(card)
                    if listing:
                        listing.location = location
                        listings.append(listing)

                self.log_success(location, "rent")

            finally:
                await browser.close()

        return listings
