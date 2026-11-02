import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.api.chat import router as chat_router
from backend.core.ingredients import (
    load_ingredient_mapping,
    load_substitutions,
    get_ranked_mealdb_recipes,
    get_substitutions,
    fetch_mealdb_details,
    extract_mealdb_ingredients,
)

load_dotenv(dotenv_path="api.env")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

mapping = load_ingredient_mapping()
substitutions_map = load_substitutions()


class IngredientRequest(BaseModel):
    ingredients: list[str]


@app.post("/recipes")
def get_recipes(request: IngredientRequest):
    ranked = get_ranked_mealdb_recipes(request.ingredients, mapping=mapping)

    for r in ranked:
        r["substitutions"] = get_substitutions(r["missed"], substitutions_map)

    return {"recipes": ranked}


@app.get("/recipes/{recipe_id}")
def get_recipe_details(recipe_id: str):
    meal = fetch_mealdb_details(recipe_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return {
        "title": meal.get("strMeal"),
        "instructions": meal.get("strInstructions"),
        "ingredients": extract_mealdb_ingredients(meal),
        "readyInMinutes": None,   # MealDB doesn't provide this
        "servings": None,         # MealDB doesn't provide this
        "sourceUrl": meal.get("strSource") or None,
    }


app.include_router(chat_router)   # adds POST /chat
