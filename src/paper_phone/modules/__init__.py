"""Page modules. Importing this package registers every module."""

from paper_phone.modules import cover, extras, language, lists, time, training, weather
from paper_phone.modules.core import REGISTRY, ModuleDef, PageCtx

__all__ = [
    "REGISTRY",
    "ModuleDef",
    "PageCtx",
    "cover",
    "extras",
    "language",
    "lists",
    "time",
    "training",
    "weather",
]
