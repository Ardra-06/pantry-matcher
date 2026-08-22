import json
import re
import requests
from sentence_transformers import util
from rapidfuzz import process, fuzz

def load_ingredient_mapping(path="backend/data/ingredient_mapping.json"):
    with open(path, "r") as f:
        return json.load(f)

def clean_ingredient_name(name):
    name = name.lower().strip()
    name = re.sub(r"^(the|a|an|a package of|a can of|a cup of)\s+", "", name)
    name = re.sub(r"\s*\d+\s*(ml|g|kg|oz|lb)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def fuzzy_match_ingredient(word, known_ingredients, threshold=80):
    match = process.extractOne(word, known_ingredients, scorer=fuzz.ratio)
    if match and match[1] >= threshold:
        return match[0]
    return word

def translate_ingredients(user_ingredients, mapping):
    translated = []
    known_words = list(mapping.keys())
    
    for ing in user_ingredients:
        ing_clean = ing.strip().lower()
        if ing_clean in mapping:
            translated.append(mapping[ing_clean])
        elif ing_clean.rstrip("s") in mapping:
            translated.append(mapping[ing_clean.rstrip("s")])
        else:
            fuzzy = fuzzy_match_ingredient(ing_clean, known_words)
            if fuzzy in mapping:
                translated.append(mapping[fuzzy])
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

def semantic_recipe_score(user_ingredients, recipe_used, recipe_missed, model):
    user_text = ", ".join(user_ingredients)
    recipe_text = ", ".join(recipe_used + recipe_missed)
    
    user_embedding = model.encode(user_text)
    recipe_embedding = model.encode(recipe_text)
    
    score = util.cos_sim(user_embedding, recipe_embedding).item()
    return round(score, 3)

def get_ranked_recipes_final(user_ingredients, api_key, mapping, model, number=10):
    translated = translate_ingredients(user_ingredients, mapping)
    raw_recipes = fetch_recipes(translated, api_key, number=number)
    summaries = [extract_recipe_summary(r) for r in raw_recipes]
    
    for s in summaries:
        s["semantic_score"] = semantic_recipe_score(user_ingredients, s["used"], s["missed"], model)
    
    ranked = sorted(
        summaries,
        key=lambda r: (r["coverage_score"], r["semantic_score"]),
        reverse=True
    )
    return ranked

def load_substitutions(path="backend/data/substitutions.json"):
    with open(path, "r") as f:
        return json.load(f)

def get_substitutions(missing_ingredients, substitutions_map):
    suggestions = {}
    for ing in missing_ingredients:
        if ing in substitutions_map:
            suggestions[ing] = substitutions_map[ing]
    return suggestions

def fetch_recipe_details(recipe_id, api_key):
    url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
    params = {"apiKey": api_key}
    response = requests.get(url, params=params)
    return response.json()
