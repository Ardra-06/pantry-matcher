import json
import requests

def load_ingredient_mapping(path="backend/data/ingredient_mapping.json"):
    with open(path, "r") as f:
        return json.load(f)

def translate_ingredients(user_ingredients, mapping):
    translated = []
    for ing in user_ingredients:
        ing_clean = ing.strip().lower()
        if ing_clean in mapping:
            translated.append(mapping[ing_clean])
        elif ing_clean.rstrip("s") in mapping:
            translated.append(mapping[ing_clean.rstrip("s")])
        else:
            translated.append(ing_clean)
    return translated

def fetch_recipes(ingredients, api_key, number=5):
    url = "https://api.spoonacular.com/recipes/findByIngredients"
    params = {
        "ingredients": ",".join(ingredients),
        "number": number,
        "apiKey": api_key
    }
    response = requests.get(url, params=params)
    return response.json()

def extract_recipe_summary(recipe):
    used = [clean_ingredient_name(ing["name"]) for ing in recipe["usedIngredients"]]
    missed = [clean_ingredient_name(ing["name"]) for ing in recipe["missedIngredients"]]
    
    total = len(used) + len(missed)
    coverage_score = len(used) / total if total > 0 else 0
    
    return {
        "id": recipe["id"],
        "title": recipe["title"],
        "used": used,
        "missed": missed,
        "coverage_score": round(coverage_score, 2)
    }
import re

def clean_ingredient_name(name):
    name = name.lower().strip()
    # remove leading articles/filler phrases
    name = re.sub(r"^(the|a|an|a package of|a can of|a cup of)\s+", "", name)
    # remove trailing measurement junk like "15 ml", "25 ml"
    name = re.sub(r"\s*\d+\s*(ml|g|kg|oz|lb)\b", "", name)
    # collapse extra whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name
def get_ranked_recipes(user_ingredients, api_key, mapping, number=10):
    translated = translate_ingredients(user_ingredients, mapping)
    raw_recipes = fetch_recipes(translated, api_key, number=number)
    summaries = [extract_recipe_summary(r) for r in raw_recipes]
    
    # sort by coverage_score, highest (most cookable) first
    ranked = sorted(summaries, key=lambda r: r["coverage_score"], reverse=True)
    return ranked