"""D6 — découpage manuel : aucun rectangle n'est proposé automatiquement."""

from __future__ import annotations

from ..core.image import Image
from .base import Detector, Rect


class ManualDetector(Detector):
    key = "manual"
    name = "Manuel"
    description = "Aucune détection : l'utilisateur trace les tuiles à la souris."
    params: list = []

    def detect(self, image: Image, p: dict) -> list[Rect]:
        return []
