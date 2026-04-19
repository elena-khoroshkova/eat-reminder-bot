from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Iterable

from PIL import Image
import torch
import torchvision.transforms as T
from torchvision.models import resnet18, ResNet18_Weights


_FOOD_WORDS = {
    # broad food-related words; ImageNet labels are english
    "pizza",
    "hamburger",
    "cheeseburger",
    "hotdog",
    "sandwich",
    "burrito",
    "taco",
    "bagel",
    "pretzel",
    "pancake",
    "waffle",
    "omelet",
    "spaghetti",
    "lasagna",
    "sushi",
    "ramen",
    "noodle",
    "soup",
    "salad",
    "guacamole",
    "chocolate",
    "candy",
    "ice cream",
    "cake",
    "cookie",
    "brownie",
    "pie",
    "doughnut",
    "espresso",
    "coffee",
    "wine",
    "beer",
    "bottle",
    "cup",
    "plate",
    "bowl",
    "banana",
    "apple",
    "orange",
    "lemon",
    "strawberry",
    "pineapple",
    "pomegranate",
    "fig",
    "grape",
    "watermelon",
    "cucumber",
    "carrot",
    "broccoli",
    "cauliflower",
    "mushroom",
    "potato",
    "tomato",
    "pepper",
    "corn",
    "bread",
    "loaf",
    "butter",
    "cheese",
    "steak",
    "meat",
    "chicken",
    "wing",
    "drumstick",
    "fish",
    "salmon",
    "tuna",
    "shrimp",
    "lobster",
    "crab",
    "egg",
    "milk",
    "yogurt",
    "rice",
}


def _normalize_label(label: str) -> str:
    s = label.lower()
    s = re.sub(r"[_-]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_foody_label(label: str) -> bool:
    s = _normalize_label(label)
    if s in _FOOD_WORDS:
        return True
    for w in _FOOD_WORDS:
        if w in s:
            return True
    return False


@dataclass(frozen=True)
class FoodCheckResult:
    is_food: bool
    best_label: str
    best_prob: float
    top: list[tuple[str, float]]


class FoodClassifier:
    """
    Lightweight heuristic "food/not-food" detector:
    - runs ResNet18 pretrained on ImageNet
    - accepts image if top predictions contain food-ish labels above threshold
    This is not perfect, but works decently for obvious food photos.
    """

    def __init__(self, *, device: str | None = None):
        self._device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        weights = ResNet18_Weights.DEFAULT
        self._model = resnet18(weights=weights).eval().to(self._device)
        self._preprocess = weights.transforms()
        self._labels = list(weights.meta["categories"])

    @torch.inference_mode()
    def check_food(self, image_bytes: bytes, *, min_confidence: float = 0.25, topk: int = 5) -> FoodCheckResult:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        x = self._preprocess(img).unsqueeze(0).to(self._device)
        logits = self._model(x)
        probs = torch.softmax(logits, dim=1)[0]
        values, indices = torch.topk(probs, k=min(topk, probs.shape[0]))

        top: list[tuple[str, float]] = []
        for v, i in zip(values.tolist(), indices.tolist(), strict=True):
            top.append((self._labels[i], float(v)))

        best_label, best_prob = top[0]
        is_food = any((_is_foody_label(lbl) and p >= min_confidence) for lbl, p in top)
        return FoodCheckResult(is_food=is_food, best_label=best_label, best_prob=float(best_prob), top=top)

