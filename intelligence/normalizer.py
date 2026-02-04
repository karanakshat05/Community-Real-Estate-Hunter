# intelligence/normalizer.py

import re
from typing import List
from datetime import datetime


def parse_price(price_str: str):
    """
    Parses Indian real estate price formats:
    ₹25,000
    25k
    ₹25k – ₹30k
    """
    if not price_str:
        return None, None, None

    s = price_str.lower().replace(",", "").replace("₹", "").strip()

    numbers = []

    for part in re.split(r"[-–to]", s):
        part = part.strip()
        if "k" in part:
            numbers.append(int(float(part.replace("k", "")) * 1000))
        elif part.isdigit():
            numbers.append(int(part))

    if not numbers:
        return None, None, None

    if len(numbers) == 1:
        return numbers[0], numbers[0], numbers[0]

    return min(numbers), max(numbers), sum(numbers) // len(numbers)


def normalize_listings(
    listings: List,
    source: str,
    location: str,
    budget_min: int | None = None,
    budget_max: int | None = None,
    buffer_pct: float = 0.2,
):
    normalized = []

    if budget_min and budget_max:
        buffered_min = int(budget_min * (1 - buffer_pct))
        buffered_max = int(budget_max * (1 + buffer_pct))
    else:
        buffered_min = buffered_max = None

    for l in listings:
        raw = l.__dict__ if hasattr(l, "__dict__") else dict(l)

        price_min, price_max, price_avg = parse_price(raw.get("price_str"))

        # Budget filter
        if buffered_min and price_avg:
            if not (buffered_min <= price_avg <= buffered_max):
                continue

        normalized.append(
            {
                "id": raw.get("id"),
                "source": source,
                "title": raw.get("title"),
                "location": location,
                "price_min": price_min,
                "price_max": price_max,
                "price_avg": price_avg,
                "area_sqft": None,  # v1
                "url": raw.get("url"),
                "image_url": raw.get("image_url"),
                "scraped_at": raw.get("scraped_at", datetime.utcnow()),
                "raw": raw,
            }
        )

    return normalized
