"""Data classes for Gumroad product data structures cached on disk.

These dataclasses mirror the structure of products stored in the cache
file (gumroad_products.json) and provide helpers to convert between
the cache format and the dataclass representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GumroadProduct:
    """Represents a single product from the Gumroad API/cache."""

    name: str
    id: str
    price: int = 0
    currency: str = "usd"
    category: str = "other"
    category_label: str = "Other"
    description: str = ""
    formatted_price: str = ""
    preview_url: str = ""
    thumbnail_url: Optional[str] = None
    main_cover_id: Optional[str] = None
    url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    custom_summary: Optional[str] = None
    sales_count: int = 0
    sales_usd_cents: float = 0.0
    require_shipping: bool = False
    customizable_price: bool = False
    custom_permalink: Optional[str] = None
    subscription_duration: Optional[str] = None
    custom_receipt: Optional[Any] = None
    custom_fields: List[Any] = field(default_factory=list)
    is_tiered_membership: bool = False
    recurrences: Optional[Any] = None
    covers: List[Any] = field(default_factory=list)
    bundle_products: List[Any] = field(default_factory=list)
    variants: List[Any] = field(default_factory=list)
    custom_delivery_url: Optional[str] = None
    deleted: bool = False
    taxonomy_id: int = 266
    max_purchase_count: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class GumroadProductsCache:
    """Represents the complete cache structure with timestamp and products list."""

    fetched_at: float
    products: List[GumroadProduct] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the entire cache to a dict suitable for JSON serialization."""
        return {
            "fetched_at": self.fetched_at,
            "products": [product.to_dict() for product in self.products],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GumroadProductsCache":
        """Create a GumroadProductsCache from a dict (typically after JSON load)."""
        products = [
            GumroadProduct(
                name=p.get("name", ""),
                id=p.get("id", ""),
                price=p.get("price", 0),
                currency=p.get("currency", "usd"),
                category=p.get("category", "other"),
                category_label=p.get("category_label", "Other"),
                description=p.get("description", ""),
                formatted_price=p.get("formatted_price", ""),
                preview_url=p.get("preview_url", ""),
                thumbnail_url=p.get("thumbnail_url"),
                main_cover_id=p.get("main_cover_id"),
                url=p.get("url"),
                tags=p.get("tags", []),
                custom_summary=p.get("custom_summary"),
                sales_count=p.get("sales_count", 0),
                sales_usd_cents=p.get("sales_usd_cents", 0.0),
                require_shipping=p.get("require_shipping", False),
                customizable_price=p.get("customizable_price", False),
                custom_permalink=p.get("custom_permalink"),
                subscription_duration=p.get("subscription_duration"),
                custom_receipt=p.get("custom_receipt"),
                custom_fields=p.get("custom_fields", []),
                is_tiered_membership=p.get("is_tiered_membership", False),
                recurrences=p.get("recurrences"),
                covers=p.get("covers", []),
                bundle_products=p.get("bundle_products", []),
                variants=p.get("variants", []),
                custom_delivery_url=p.get("custom_delivery_url"),
                deleted=p.get("deleted", False),
                taxonomy_id=p.get("taxonomy_id", 266),
                max_purchase_count=p.get("max_purchase_count"),
            )
            for p in data.get("products", [])
        ]
        return cls(fetched_at=data.get("fetched_at", 0), products=products)


@dataclass
class GumroadProductSimple:
    """A minimal product dataclass with only name and id - useful for simple caching."""

    name: str
    id: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to a simple dict with only name and id keys."""
        return {"name": self.name, "id": self.id}


def products_from_cache(data: Dict[str, Any]) -> List[GumroadProduct]:
    """Parse and return a list of GumroadProduct instances from cache JSON data."""
    return GumroadProductsCache.from_dict(data).products


def products_to_cache(products: List[GumroadProduct], fetched_at: float) -> Dict[str, Any]:
    """Convert a list of products and timestamp to the cache JSON dict format."""
    return GumroadProductsCache(fetched_at=fetched_at, products=products).to_dict()