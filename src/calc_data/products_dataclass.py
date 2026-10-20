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
    preview_url: Optional[str] = None
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
    short_url: Optional[str] = None
    landing_url: Optional[str] = None
    published: bool = True
    file_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization, excluding None values."""
        return {
            attribute_name: attribute_value
            for attribute_name, attribute_value in self.__dict__.items()
            if attribute_value is not None
        }


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
        raw_products_list = data.get("products")
        if raw_products_list is None and isinstance(data.get("response"), dict):
            raw_products_list = data["response"].get("products", [])
        elif raw_products_list is None:
            raw_products_list = []

        products = [
            GumroadProduct(
                name=product_dictionary.get("name", ""),
                id=product_dictionary.get("id", ""),
                price=product_dictionary.get("price", 0),
                currency=product_dictionary.get("currency", "usd"),
                category=product_dictionary.get("category", "other"),
                category_label=product_dictionary.get("category_label", "Other"),
                description=product_dictionary.get("description", ""),
                formatted_price=product_dictionary.get("formatted_price", ""),
                preview_url=product_dictionary.get("preview_url"),
                thumbnail_url=product_dictionary.get("thumbnail_url"),
                main_cover_id=product_dictionary.get("main_cover_id"),
                url=product_dictionary.get("url"),
                tags=product_dictionary.get("tags", []),
                custom_summary=product_dictionary.get("custom_summary"),
                sales_count=product_dictionary.get("sales_count", 0),
                sales_usd_cents=product_dictionary.get("sales_usd_cents", 0.0),
                require_shipping=product_dictionary.get("require_shipping", False),
                customizable_price=product_dictionary.get("customizable_price", False),
                custom_permalink=product_dictionary.get("custom_permalink"),
                subscription_duration=product_dictionary.get("subscription_duration"),
                custom_receipt=product_dictionary.get("custom_receipt"),
                custom_fields=product_dictionary.get("custom_fields", []),
                is_tiered_membership=product_dictionary.get("is_tiered_membership", False),
                recurrences=product_dictionary.get("recurrences"),
                covers=product_dictionary.get("covers", []),
                bundle_products=product_dictionary.get("bundle_products", []),
                variants=product_dictionary.get("variants", []),
                custom_delivery_url=product_dictionary.get("custom_delivery_url"),
                deleted=product_dictionary.get("deleted", False),
                taxonomy_id=product_dictionary.get("taxonomy_id", 266),
                max_purchase_count=product_dictionary.get("max_purchase_count"),
                short_url=product_dictionary.get("short_url"),
                landing_url=product_dictionary.get("landing_url"),
                published=product_dictionary.get("published", True),
                file_info=product_dictionary.get("file_info", {}),
            )
            for product_dictionary in raw_products_list
        ]
        return cls(fetched_at=data.get("fetched_at", 0.0), products=products)


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
