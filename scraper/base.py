from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScrapedListing:
    """
    The Standardized Data Model.
    Every house found by any scraper (Housing, MagicBricks, etc.)
    must be converted into this format.
    """
    id: str  # Unique ID (e.g., "Housing-12345")
    source: str  # Website name
    url: str  # Direct link
    raw_text: str  # Full text for the AI Parser
    scraped_at: datetime = field(default_factory=datetime.now)
    price_str: str = "0"
    title: str = "Unknown"
    location: str = "Unknown"
    image_url: Optional[str] = None


class BaseScraper(ABC):
    """
    The Scraper Blueprint.
    Handles the common setup and logic for all housing bots.
    """

    def __init__(self, headless: bool = True, timeout: int = 60000):
        self.headless = headless
        self.timeout = timeout
        self.source_name = "Base"

    @abstractmethod
    async def scrape(self, location: str, budget_min: int, budget_max: int, **kwargs) -> List[ScrapedListing]:
        """
        All scrapers must implement this specific method.
        """
        pass

    def _make_id(self, raw_id: str) -> str:
        """Standardizes IDs to prevent duplicates (e.g., 'Housing-10293')."""
        return f"{self.source_name}-{raw_id}"

    def _validate_budget(self, min_b: int, max_b: int):
        """Sanity check to ensure budget ranges make sense."""
        if min_b > max_b:
            print(f"⚠️  Warning: Min budget ({min_b}) is higher than Max ({max_b}). Swapping them.")
            return max_b, min_b
        return min_b, max_b

    def log_success(self, location: str, category: str):
        """Hook for future cache logging."""
        print(f"✅ [{self.source_name}] Successfully found results for {location} ({category})")

    def log_failure(self, location: str, category: str):
        """Hook for future health tracking."""
        print(f"❌ [{self.source_name}] No results or error for {location} ({category})")