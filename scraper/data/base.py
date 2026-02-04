"""
Base classes and data models for the Community Real Estate Hunter scraping module.

All scrapers must inherit from BaseScraper and return ScrapedListing objects.
The cache layer is automatically available to all scrapers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field
from datetime import datetime
import sys
import os

# Ensure the project root is in the path for internal imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.cache_manager import ScraperCache


# ============================================================================
# EXCEPTIONS
# ============================================================================

class ScraperException(Exception):
    """Base exception for all scraper errors"""
    pass


class URLDiscoveryError(ScraperException):
    """Raised when URL discovery fails"""
    pass


class HashBrokenError(ScraperException):
    """Raised when cached hash is broken and cannot be recovered"""
    pass


class ScrapingTimeoutError(ScraperException):
    """Raised when scraping operation times out"""
    pass


class AntiBotDetectedError(ScraperException):
    """Raised when anti-bot measures are detected"""
    pass


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ScrapedListing:
    """
    Standardized output for all real estate scrapers.

    This is the raw data structure returned by scrapers.
    The parser (SLM) will extract structured fields from raw_text.
    """
    # Required fields
    id: str  # Unique ID (e.g., "housing-12345")
    source: str  # Source website: "housing", "magicbricks", etc.
    url: str  # Direct link to listing
    raw_text: str  # Complete card text for LLM to parse

    # Auto-populated fields
    scraped_at: datetime = field(default_factory=lambda: datetime.now())

    # Semi-structured fields (extracted if easy during scraping)
    price_str: str = "0"
    title: str = "Unknown"
    location: str = "Unknown"
    image_url: Optional[str] = None

    # Metadata for tracking
    metadata: Dict = field(default_factory=dict)


@dataclass
class ScraperStats:
    """
    Tracks performance and health of a scraping run.

    Used for monitoring and debugging scraper behavior.
    """
    source: str
    location: str
    success_count: int = 0
    failure_count: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now())

    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return (self.success_count / total) * 100

    def total_attempts(self) -> int:
        """Total number of scraping attempts"""
        return self.success_count + self.failure_count

    def duration(self) -> float:
        """Duration of scraping run in seconds"""
        return (datetime.now() - self.start_time).total_seconds()


# ============================================================================
# BASE SCRAPER
# ============================================================================

class BaseScraper(ABC):
    """
    Abstract base class for all site-specific scrapers.

    Provides:
    - Shared access to ScraperCache
    - Common utility methods
    - Standardized interface
    - Health tracking integration

    All scrapers must implement the scrape() method.
    """

    def __init__(
            self,
            source_name: str = "base",
            headless: bool = True,
            timeout: int = 60000
    ):
        """
        Initialize the scraper.

        Args:
            source_name: Name of the source website (e.g., "housing")
            headless: Run browser in headless mode
            timeout: Timeout in milliseconds for page loads
        """
        self.source_name = source_name.lower()
        self.headless = headless
        self.timeout = timeout

        # Initialize the ScraperCache
        self.scraper_cache = ScraperCache()

    @abstractmethod
    async def scrape(
            self,
            location: str,
            budget_min: int,
            budget_max: int,
            **kwargs
    ) -> List[ScrapedListing]:
        """
        Main scraping method - must be implemented by each scraper.

        Args:
            location: Target location (e.g., "Gurugram", "Sector 56")
            budget_min: Minimum budget in rupees
            budget_max: Maximum budget in rupees
            **kwargs: Additional scraper-specific parameters

        Returns:
            List of ScrapedListing objects

        Raises:
            ScraperException: If scraping fails critically
        """
        pass

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def _make_id(self, raw_id: str) -> str:
        """
        Create a globally unique ID for a listing.

        Args:
            raw_id: Raw ID from the source website

        Returns:
            Formatted ID like "housing-12345"
        """
        # Clean the raw_id
        clean_id = raw_id.replace(" ", "-").replace("/", "-")
        return f"{self.source_name}-{clean_id}"

    def _validate_budget(self, min_b: int, max_b: int) -> Tuple[int, int]:
        """
        Validate and possibly swap budget range.

        Args:
            min_b: Minimum budget
            max_b: Maximum budget

        Returns:
            Tuple of (min_budget, max_budget) in correct order
        """
        if min_b > max_b:
            print(f"Warning: Min budget {min_b} > Max budget {max_b}. Swapping.")
            return max_b, min_b

        if min_b < 0:
            print(f"Warning: Negative budget {min_b}, setting to 0")
            min_b = 0

        return min_b, max_b

    def _normalize_location(self, location: str) -> str:
        """
        Normalize location name for consistent cache keys.

        Args:
            location: Location name (e.g., "Sector 56", "GURUGRAM")

        Returns:
            Normalized location (e.g., "sector-56", "gurugram")
        """
        return location.lower().replace(" ", "-")

    # ========================================================================
    # CACHE INTEGRATION METHODS
    # ========================================================================

    def log_success(self, location: str, bhk: str):
        """
        Mark a successful scrape in the cache.

        This updates the health tracking for the cached hash.

        Args:
            location: Location that was scraped
            bhk: BHK type that was scraped
        """
        self.scraper_cache.mark_success(self.source_name, location, bhk)

    def log_failure(self, location: str, bhk: str):
        """
        Mark a failed scrape in the cache.

        This updates the health tracking and may trigger auto-healing.

        Args:
            location: Location that failed to scrape
            bhk: BHK type that failed to scrape
        """
        self.scraper_cache.mark_failure(self.source_name, location, bhk)

    def get_cached_bhk_types(self, location: str) -> List[str]:
        """
        Get all cached BHK types for a location.

        Args:
            location: Location to check

        Returns:
            List of BHK types (e.g., ["1bhk", "2bhk"])
        """
        return self.scraper_cache.get_all_bhk_types(self.source_name, location)

    def has_cached_location(self, location: str) -> bool:
        """
        Check if location has any cached data.

        Args:
            location: Location to check

        Returns:
            True if location exists in cache
        """
        return self.scraper_cache.has_location(self.source_name, location)

    # ========================================================================
    # CONTEXT MANAGER SUPPORT (Optional - for resource cleanup)
    # ========================================================================

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.

        Child classes can override to cleanup resources (close browsers, etc.)
        """
        pass

    # ========================================================================
    # STRING REPRESENTATION
    # ========================================================================

    def __repr__(self) -> str:
        """String representation of scraper"""
        return f"{self.__class__.__name__}(source='{self.source_name}', headless={self.headless})"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_price_number(price_str: str) -> int:
    """
    Extract numeric price from string.

    Args:
        price_str: Price string like "₹ 22,000" or "Rs. 25000"

    Returns:
        Integer price or 0 if cannot parse

    Examples:
        "₹ 22,000" -> 22000
        "Rs. 25000" -> 25000
        "25K" -> 25000
    """
    import re

    # Remove currency symbols and commas
    clean = price_str.replace('₹', '').replace('Rs.', '').replace(',', '').strip()

    # Handle K (thousands)
    if 'K' in clean.upper():
        clean = clean.upper().replace('K', '000')

    # Extract first number
    match = re.search(r'\d+', clean)
    if match:
        return int(match.group())

    return 0


if __name__ == "__main__":
    # Quick test
    print("🧪 Testing base.py\n")

    # Test ScrapedListing
    listing = ScrapedListing(
        id="housing-12345",
        source="housing",
        url="https://housing.com/...",
        raw_text="2 BHK Apartment\n₹ 22,000\n1200 sqft",
        price_str="₹ 22,000",
        title="2 BHK in Sector 56",
        location="Gurugram"
    )

    print(f"✅ Created listing: {listing.id}")
    print(f"   Scraped at: {listing.scraped_at}")

    # Test ScraperStats
    stats = ScraperStats(source="housing", location="Gurugram")
    stats.success_count = 3
    stats.failure_count = 1

    print(f"\n✅ Stats: {stats.success_rate():.1f}% success rate")
    print(f"   Duration: {stats.duration():.2f}s")

    # Test price extraction
    price = extract_price_number("₹ 22,000")
    print(f"\n✅ Extracted price: {price}")