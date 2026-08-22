from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from backend.core.ingredients import load_ingredient_mapping, load_substitutions, get_ranked_recipes_final, get_substitutions
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="api.env")
api_key = os.getenv("SPOONACULAR_API_KEY")

app = FastAPI()

mapping = load_ingredient_mapping()
substitutions_map = load_substitutions()
model = SentenceTransformer('all-MiniLM-L6-v2')

class IngredientRequest(BaseModel):
    ingredients: list[str]

@app.post("/recipes")
def get_recipes(request: IngredientRequest):
    ranked = get_ranked_recipes_final(request.ingredients, api_key, mapping, model)
    
    for r in ranked:
        r["substitutions"] = get_substitutions(r["missed"], substitutions_map)
    
    return {"recipes": ranked}
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
from backend.core.ingredients import fetch_recipe_details

@app.get("/recipes/{recipe_id}")
def get_recipe_details(recipe_id: int):
    details = fetch_recipe_details(recipe_id, api_key)
    return {
        "title": details.get("title"),
        "instructions": details.get("instructions"),
        "readyInMinutes": details.get("readyInMinutes"),
        "servings": details.get("servings"),
        "sourceUrl": details.get("sourceUrl")
    }

