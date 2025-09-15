import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx

from app.skills.recipe_skill import RecipeSkill

DATA = {
    "meals": [
        {
            "strMeal": "Guacamole",
            "strInstructions": "Mash avocados. Add lime. Serve.",
            "strIngredient1": "Avocado",
            "strMeasure1": "2",
            "strIngredient2": "Lime",
            "strMeasure2": "1",
            "strIngredient3": "Salt",
            "strMeasure3": "1 tsp",
        }
    ]
}


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self):
                return DATA

            def raise_for_status(self):
                pass

        return R()


def test_recipe(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = RecipeSkill()
    m = skill.match("how do i make guacamole")
    out = asyncio.run(skill.run("how do i make guacamole", m))
    assert "Guacamole" in out
    assert "Avocado" in out
    assert "Mash avocados" in out
