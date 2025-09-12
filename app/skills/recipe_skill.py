from __future__ import annotations

# app/skills/recipe_skill.py
import re

import httpx

from .base import Skill


class RecipeSkill(Skill):
    PATTERNS = [
        re.compile(r"^how do i make (?P<dish>.+)", re.I),
        re.compile(r"^recipe for (?P<dish>.+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        dish = match.group("dish").strip()
        url = "https://www.themealdb.com/api/json/v1/1/search.php"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"s": dish})
            resp.raise_for_status()
            data = resp.json()
        meals = data.get("meals")
        if not meals:
            return f"No recipe found for {dish}."
        meal = meals[0]
        ingredients = []
        for i in range(1, 21):
            ing = meal.get(f"strIngredient{i}")
            meas = meal.get(f"strMeasure{i}")
            if ing and ing.strip():
                part = (
                    f"{meas.strip()} {ing.strip()}"
                    if meas and meas.strip()
                    else ing.strip()
                )
                ingredients.append(part.strip())
        instructions = meal.get("strInstructions", "").strip()
        ing_text = "; ".join(ingredients[:5])
        instr = instructions.split(".")
        instr_text = ". ".join(instr[:2]).strip()
        return f"{meal['strMeal']} ingredients: {ing_text}. Instructions: {instr_text}."
