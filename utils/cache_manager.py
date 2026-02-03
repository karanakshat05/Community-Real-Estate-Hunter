# import json
# import os
# from typing import Dict, Any, Optional
#
#
# class BaseCache:
#     """
#     PARENT CLASS: The Foundation.
#     Handles the low-level JSON I/O. This class doesn't know about
#     real estate; it only knows how to manage files and dictionaries.
#     """
#
#     def __init__(self, filename: str):
#         self.filepath = os.path.join("data", filename)
#         # Ensure the data directory exists globally
#         os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
#         self.data = self._load()
#
#     def _load(self) -> Dict:
#         """Loads JSON data from disk or returns an empty dict if not found."""
#         if os.path.exists(self.filepath):
#             try:
#                 with open(self.filepath, 'r') as f:
#                     return json.load(f)
#             except Exception as e:
#                 print(f"[BaseCache] ⚠️ Corruption detected in {self.filepath}: {e}")
#                 return {}
#         return {}
#
#     def save(self):
#         """Writes the current state of self.data to the JSON file."""
#         try:
#             with open(self.filepath, 'w') as f:
#                 json.dump(self.data, f, indent=4)
#         except Exception as e:
#             print(f"[BaseCache] ❌ Failed to write to disk: {e}")
#
#     def get(self, key: str, default: Any = None) -> Any:
#         return self.data.get(key, default)
#
#     def set(self, key: str, value: Any):
#         self.data[key] = value
#         self.save()
#
#
# class ScraperCache(BaseCache):
#     """
#     DERIVED CLASS: The Real Estate Specialist.
#     Translates site names, locations, and BHK types into organized storage.
#
#     This handles:
#     1. URL Hashes (Location mappings)
#     2. Scraper-specific metadata (Last successful selector used)
#     """
#
#     def __init__(self):
#         # All scraper metadata goes into this specific file
#         super().__init__("scraper_metadata.json")
#
#     def get_hash(self, source: str, location: str, category: str = "default") -> Optional[str]:
#         """
#         Retrieves a site-specific hash.
#         Example: cache.get_hash("housing", "sector-56", "2bhk")
#         """
#         source = source.lower()
#         loc_key = location.lower().replace(" ", "-")
#
#         source_group = self.get(source, {})
#         location_group = source_group.get(loc_key, {})
#         return location_group.get(category)
#
#     def set_hash(self, source: str, location: str, hash_value: str, category: str = "default"):
#         """
#         Saves a newly discovered hash for a location.
#         """
#         source = source.lower()
#         loc_key = location.lower().replace(" ", "-")
#
#         if source not in self.data:
#             self.data[source] = {}
#         if loc_key not in self.data[source]:
#             self.data[source][loc_key] = {}
#
#         self.data[source][loc_key][category] = hash_value
#         self.save()
#         print(f"[ScraperCache] ✨ Learned {source.upper()} hash for {loc_key} ({category})")
#
#     def invalidate(self, source: str, location: str, category: str = "default"):
#         """Removes a hash if the site says 'Page not found'."""
#         source = source.lower()
#         loc_key = location.lower().replace(" ", "-")
#         try:
#             if source in self.data and loc_key in self.data[source]:
#                 del self.data[source][loc_key][category]
#                 self.save()
#                 print(f"[ScraperCache] 🗑️ Cleaned stale hash for {loc_key}")
#         except KeyError:
#             pass
#
#
# class SessionCache(BaseCache):
#     """
#     DERIVED CLASS: Auth & Session specialist.
#     Used to store browser cookies/sessions so we don't have to
#     re-login or deal with 'New User' detection every run.
#     """
#
#     def __init__(self):
#         super().__init__("browser_sessions.json")
#
#     def save_session(self, source: str, cookies: list):
#         self.set(source.lower(), {
#             "cookies": cookies,
#             "updated_at": os.times()[4]  # Rough timestamp
#         })
#
#     def get_session(self, source: str) -> Optional[list]:
#         session = self.get(source.lower())
#         return session.get("cookies") if session else None
#
# # Example of how we might use another specialized cache for AI Agent memory later:
# # class IntelligenceCache(BaseCache):
# #     def __init__(self):
# #         super().__init__("llm_reasoning.json")


"""
Cache Manager for Community Real Estate Hunter

Provides caching infrastructure for scrapers to store and retrieve
metadata, sessions, and improve performance through intelligent caching.

Cache Types:
- ScraperCache: Stores location hashes and URL patterns
- SessionCache: Stores browser sessions and cookies (for future use)
"""

import json
from pathlib import Path
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from enum import Enum


class CacheStatus(Enum):
    """Health status of cached entries"""
    HEALTHY = "healthy"  # Working well
    DEGRADED = "degraded"  # Some failures, still usable
    BROKEN = "broken"  # High failure rate, should rediscover


@dataclass
class CachedEntry:
    """Base class for cached entries with health tracking"""
    discovered_at: str
    last_used: str
    success_count: int
    failure_count: int
    status: str

    def is_healthy(self) -> bool:
        """Check if entry is in healthy state"""
        return self.status == CacheStatus.HEALTHY.value

    def is_degraded(self) -> bool:
        """Check if entry is degraded but still usable"""
        return self.status == CacheStatus.DEGRADED.value

    def is_broken(self) -> bool:
        """Check if entry is broken and needs rediscovery"""
        return self.status == CacheStatus.BROKEN.value

    def failure_rate(self) -> float:
        """Calculate failure rate"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.failure_count / total

    def update_status(self):
        """Update status based on failure rate"""
        rate = self.failure_rate()

        if rate == 0 or (self.success_count > 5 and rate < 0.1):
            self.status = CacheStatus.HEALTHY.value
        elif rate < 0.3:  # Less than 30% failure
            self.status = CacheStatus.DEGRADED.value
        else:
            self.status = CacheStatus.BROKEN.value


@dataclass
class ScraperHashEntry(CachedEntry):
    """Cached hash entry for a specific site/location/bhk combination"""
    hash: str
    full_url: str
    bhk_code: Optional[str] = None
    location_hash: Optional[str] = None


class BaseCache(ABC):
    """
    Abstract base class for all cache types.

    Handles JSON file I/O and provides common caching operations.
    All derived caches should implement specific get/set logic.
    """

    def __init__(self, cache_file: str, data_dir: str = "data"):
        """
        Initialize cache with file path.

        Args:
            cache_file: Name of the JSON cache file
            data_dir: Directory to store cache files (default: "data")
        """
        self.data_dir = Path(data_dir)
        self.cache_file = self.data_dir / cache_file

        # Create data directory if it doesn't exist
        self.data_dir.mkdir(exist_ok=True)

        # Load existing cache or create new
        self.data = self._load()

    def _load(self) -> dict:
        """Load cache from JSON file"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"⚠️  Cache file corrupted, creating new: {self.cache_file}")
                return self._get_empty_structure()
        else:
            print(f"📝 Creating new cache file: {self.cache_file}")
            return self._get_empty_structure()

    def _save(self):
        """Save cache to JSON file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"❌ Failed to save cache: {e}")

    @abstractmethod
    def _get_empty_structure(self) -> dict:
        """Return the initial empty structure for this cache type"""
        pass

    def clear(self):
        """Clear all cache data"""
        self.data = self._get_empty_structure()
        self._save()
        print(f"🗑️  Cache cleared: {self.cache_file}")

    def get_stats(self) -> dict:
        """Get cache statistics"""
        return {
            "file": str(self.cache_file),
            "size_bytes": self.cache_file.stat().st_size if self.cache_file.exists() else 0,
            "last_modified": datetime.fromtimestamp(
                self.cache_file.stat().st_mtime
            ).isoformat() if self.cache_file.exists() else None
        }


class ScraperCache(BaseCache):
    """
    Cache for scraper metadata (location hashes, URL patterns).

    Structure:
    {
      "metadata": {
        "version": "1.0",
        "last_updated": "2026-02-03T10:30:00"
      },
      "sites": {
        "housing": {
          "gurugram": {
            "1bhk": {
              "hash": "C2P1od1w26jrfqap1jl",
              "full_url": "https://housing.com/...",
              "bhk_code": "C2",
              "location_hash": "P1od1w26jrfqap1jl",
              "discovered_at": "2026-02-03T10:30:00",
              "last_used": "2026-02-03T14:20:00",
              "success_count": 15,
              "failure_count": 0,
              "status": "healthy"
            }
          }
        }
      }
    }
    """

    def __init__(self, cache_file: str = "scraper_metadata.json", data_dir: str = "data"):
        super().__init__(cache_file, data_dir)

    def _get_empty_structure(self) -> dict:
        """Initialize empty scraper cache structure"""
        return {
            "metadata": {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            },
            "sites": {}
        }

    def _normalize_location(self, location: str) -> str:
        """Normalize location name for consistent cache keys"""
        return location.lower().replace(" ", "-")

    def _update_metadata(self):
        """Update cache metadata timestamp"""
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()

    def get(self, site: str, location: str, bhk: str) -> Optional[ScraperHashEntry]:
        """
        Retrieve cached hash entry.

        Args:
            site: Website name (e.g., "housing", "magicbricks")
            location: Location name (e.g., "Gurugram", "Sector 56")
            bhk: BHK type (e.g., "1bhk", "2bhk")

        Returns:
            ScraperHashEntry if found, None otherwise
        """
        location_key = self._normalize_location(location)

        try:
            entry_data = self.data["sites"][site][location_key][bhk]
            entry = ScraperHashEntry(**entry_data)

            # Update last_used timestamp
            entry.last_used = datetime.now().isoformat()
            self.data["sites"][site][location_key][bhk]["last_used"] = entry.last_used
            self._save()

            return entry
        except KeyError:
            return None

    def set(
            self,
            site: str,
            location: str,
            bhk: str,
            hash: str,
            full_url: str,
            bhk_code: Optional[str] = None,
            location_hash: Optional[str] = None
    ):
        """
        Store hash entry in cache.

        Args:
            site: Website name
            location: Location name
            bhk: BHK type
            hash: Hash value
            full_url: Complete URL
            bhk_code: BHK code portion of hash (optional)
            location_hash: Location portion of hash (optional)
        """
        location_key = self._normalize_location(location)
        now = datetime.now().isoformat()

        # Create nested structure if needed
        if site not in self.data["sites"]:
            self.data["sites"][site] = {}
        if location_key not in self.data["sites"][site]:
            self.data["sites"][site][location_key] = {}

        # Create new entry
        entry = ScraperHashEntry(
            hash=hash,
            full_url=full_url,
            bhk_code=bhk_code,
            location_hash=location_hash,
            discovered_at=now,
            last_used=now,
            success_count=0,
            failure_count=0,
            status=CacheStatus.HEALTHY.value
        )

        self.data["sites"][site][location_key][bhk] = asdict(entry)
        self._update_metadata()
        self._save()

        print(f"💾 Cached hash for {site}/{location}/{bhk}")

    def mark_success(self, site: str, location: str, bhk: str):
        """
        Mark a successful scrape using cached hash.

        Args:
            site: Website name
            location: Location name
            bhk: BHK type
        """
        entry = self.get(site, location, bhk)
        if entry:
            entry.success_count += 1
            entry.update_status()

            location_key = self._normalize_location(location)
            self.data["sites"][site][location_key][bhk]["success_count"] = entry.success_count
            self.data["sites"][site][location_key][bhk]["status"] = entry.status
            self._save()

    def mark_failure(self, site: str, location: str, bhk: str):
        """
        Mark a failed scrape using cached hash.

        Args:
            site: Website name
            location: Location name
            bhk: BHK type
        """
        entry = self.get(site, location, bhk)
        if entry:
            entry.failure_count += 1
            entry.update_status()

            location_key = self._normalize_location(location)
            self.data["sites"][site][location_key][bhk]["failure_count"] = entry.failure_count
            self.data["sites"][site][location_key][bhk]["status"] = entry.status
            self._save()

            if entry.is_broken():
                print(
                    f"⚠️  Hash marked as BROKEN for {site}/{location}/{bhk} (failure rate: {entry.failure_rate():.1%})")

    def has_location(self, site: str, location: str) -> bool:
        """
        Check if we have any cached data for a location.

        Args:
            site: Website name
            location: Location name

        Returns:
            True if location exists in cache
        """
        location_key = self._normalize_location(location)
        return site in self.data["sites"] and location_key in self.data["sites"][site]

    def get_all_bhk_types(self, site: str, location: str) -> list:
        """
        Get all cached BHK types for a location.

        Args:
            site: Website name
            location: Location name

        Returns:
            List of BHK types (e.g., ["1bhk", "2bhk"])
        """
        location_key = self._normalize_location(location)

        try:
            return list(self.data["sites"][site][location_key].keys())
        except KeyError:
            return []

    def print_summary(self):
        """Print a summary of cached entries"""
        print("\n" + "=" * 70)
        print("📊 SCRAPER CACHE SUMMARY")
        print("=" * 70)

        metadata = self.data.get("metadata", {})
        print(f"\n📅 Last Updated: {metadata.get('last_updated', 'Unknown')}")

        total_entries = 0
        for site, locations in self.data.get("sites", {}).items():
            print(f"\n🌐 Site: {site.upper()}")
            for location, bhk_data in locations.items():
                bhk_count = len(bhk_data)
                total_entries += bhk_count

                # Show health status
                healthy = sum(1 for b in bhk_data.values() if b.get('status') == 'healthy')
                degraded = sum(1 for b in bhk_data.values() if b.get('status') == 'degraded')
                broken = sum(1 for b in bhk_data.values() if b.get('status') == 'broken')

                status_str = f"✅ {healthy}" if healthy else ""
                if degraded:
                    status_str += f" ⚠️ {degraded}" if status_str else f"⚠️ {degraded}"
                if broken:
                    status_str += f" ❌ {broken}" if status_str else f"❌ {broken}"

                print(f"  📍 {location}: {bhk_count} BHK types ({status_str})")

        print(f"\n📈 Total Entries: {total_entries}")
        print("=" * 70 + "\n")


class SessionCache(BaseCache):
    """
    Cache for browser sessions (cookies, user agents, tokens).

    Structure:
    {
      "metadata": {
        "version": "1.0",
        "last_updated": "2026-02-03T10:30:00"
      },
      "sessions": {
        "housing": {
          "cookies": [...],
          "user_agent": "Mozilla/5.0 ...",
          "viewport": {"width": 1920, "height": 1080},
          "created_at": "2026-02-03T10:00:00",
          "last_refreshed": "2026-02-03T14:00:00",
          "usage_count": 25,
          "status": "active"
        }
      }
    }
    """

    def __init__(self, cache_file: str = "browser_sessions.json", data_dir: str = "data"):
        super().__init__(cache_file, data_dir)

    def _get_empty_structure(self) -> dict:
        """Initialize empty session cache structure"""
        return {
            "metadata": {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            },
            "sessions": {}
        }

    def get(self, site: str) -> Optional[dict]:
        """
        Retrieve cached session data.

        Args:
            site: Website name (e.g., "housing", "magicbricks")

        Returns:
            Session data dict if found and valid, None otherwise
        """
        try:
            session = self.data["sessions"][site]

            # Check if session is still valid (not expired)
            if self._is_session_valid(session):
                # Update usage count
                session["usage_count"] = session.get("usage_count", 0) + 1
                session["last_used"] = datetime.now().isoformat()
                self._save()
                return session
            else:
                print(f"⚠️  Session expired for {site}")
                return None
        except KeyError:
            return None

    def set(
            self,
            site: str,
            cookies: list,
            user_agent: str,
            viewport: dict = None
    ):
        """
        Store session data.

        Args:
            site: Website name
            cookies: List of cookie dicts
            user_agent: User agent string
            viewport: Viewport dimensions (optional)
        """
        now = datetime.now().isoformat()

        session = {
            "cookies": cookies,
            "user_agent": user_agent,
            "viewport": viewport or {"width": 1920, "height": 1080},
            "created_at": now,
            "last_refreshed": now,
            "last_used": now,
            "usage_count": 0,
            "status": "active"
        }

        self.data["sessions"][site] = session
        self.data["metadata"]["last_updated"] = now
        self._save()

        print(f"💾 Cached session for {site}")

    def _is_session_valid(self, session: dict) -> bool:
        """Check if session hasn't expired"""
        # Sessions valid for 24 hours
        last_refresh = datetime.fromisoformat(session.get("last_refreshed"))
        age = datetime.now() - last_refresh
        return age < timedelta(hours=24)

    def refresh_session(self, site: str):
        """Mark session as refreshed"""
        if site in self.data["sessions"]:
            self.data["sessions"][site]["last_refreshed"] = datetime.now().isoformat()
            self._save()


# Convenience functions for easy access
def get_scraper_cache() -> ScraperCache:
    """Get singleton instance of ScraperCache"""
    return ScraperCache()


def get_session_cache() -> SessionCache:
    """Get singleton instance of SessionCache"""
    return SessionCache()


if __name__ == "__main__":
    # Test the cache manager
    print("🧪 Testing Cache Manager\n")

    # Test ScraperCache
    cache = ScraperCache()

    # Add some test data
    cache.set(
        site="housing",
        location="Gurugram",
        bhk="1bhk",
        hash="C2P1od1w26jrfqap1jl",
        full_url="https://housing.com/rent/1bhk-flats-for-rent-in-gurugram-haryana-C2P1od1w26jrfqap1jl",
        bhk_code="C2",
        location_hash="P1od1w26jrfqap1jl"
    )

    # Retrieve it
    entry = cache.get("housing", "Gurugram", "1bhk")
    if entry:
        print(f"✅ Retrieved: {entry.hash}")
        print(f"   Status: {entry.status}")
        print(f"   URL: {entry.full_url[:60]}...")

    # Mark some successes
    for _ in range(10):
        cache.mark_success("housing", "Gurugram", "1bhk")

    # Mark some failures
    for _ in range(2):
        cache.mark_failure("housing", "Gurugram", "1bhk")

    # Check status
    entry = cache.get("housing", "Gurugram", "1bhk")
    print(f"\n📊 After 10 successes, 2 failures:")
    print(f"   Failure rate: {entry.failure_rate():.1%}")
    print(f"   Status: {entry.status}")

    # Print summary
    cache.print_summary()