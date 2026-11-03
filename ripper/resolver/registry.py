"""
HandlerRegistry: Discovers, registers, and routes URLs to site-specific resolver handlers.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from .base import BaseResolverHandler


class HandlerRegistry:
    """Central registry of site-specific resolver handlers."""

    def __init__(self) -> None:
        self._handlers: List[BaseResolverHandler] = []

    def register(self, handler: BaseResolverHandler) -> None:
        """Register a handler and keep the list sorted by priority."""
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.priority)

    def get_handler(self, url: str, html: Optional[str] = None) -> Optional[BaseResolverHandler]:
        """Find the highest-priority handler capable of processing this URL/HTML."""
        for handler in self._handlers:
            try:
                if handler.can_handle(url, html):
                    return handler
            except Exception:
                continue
        return None

    def all_handlers(self) -> List[BaseResolverHandler]:
        return list(self._handlers)

    def auto_discover(self, package_name: str = "ripper.resolver.handlers") -> int:
        """Dynamically discover and register all BaseResolverHandler subclasses in a package."""
        import importlib
        import inspect
        import pkgutil

        discovered = 0
        try:
            pkg = importlib.import_module(package_name)
            pkg_path = getattr(pkg, "__path__", None)
            if not pkg_path:
                return 0

            existing_types = {type(h) for h in self._handlers}

            for _, modname, _ in pkgutil.iter_modules(pkg_path):
                if modname.startswith("_"):
                    continue
                try:
                    mod = importlib.import_module(f"{package_name}.{modname}")
                    for _, cls in inspect.getmembers(mod, inspect.isclass):
                        if (
                            issubclass(cls, BaseResolverHandler)
                            and cls is not BaseResolverHandler
                            and cls not in existing_types
                        ):
                            self.register(cls())
                            existing_types.add(cls)
                            discovered += 1
                except Exception:
                    continue
        except Exception:
            return 0
        return discovered


# Global registry instance
GLOBAL_REGISTRY = HandlerRegistry()

