from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ScrapedListing:
    id: str  # Unique ID (e.g., "MB-20931")
    source: str  # "Housing", "MagicBricks", "99acres"
    url: str  # Direct link
    raw_text: str  # Full text for the SLM to parse later
    price_str: str  # Extracted string like "₹ 20,000"
    title: str  # e.g., "1 BHK Flat in Sector 56"
    location: str  # e.g., "Kendriya Vihar, Gurgaon"
    image_url: Optional[str] = None


class BaseScraper(ABC):
    """
    Abstract Base Class that all specific site scrapers must inherit from.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless

    @abstractmethod
    async def scrape(self, location: str, budget: int, high_rise: bool = False) -> List[ScrapedListing]:
        """
        The main entry point.
        Must return a list of ScrapedListing objects.
        """
        pass

    def _make_id(self, source: str, raw_id: str) -> str:
        """Helper to create consistent IDs"""
        return f"{source}-{raw_id}"