import json
import os
import re
import time
import httpx
import requests
from google import genai
from google.genai import types
from google.genai.errors import APIError
from rapidfuzz import process, fuzz
from sentence_transformers import util


# --- Ingredient translation & cleaning ---

def load_ingredient_mapping(path="backend/data/ingredient_mapping.json"):
    with open(path, "r") as f:
        return json.load(f)


def load_substitutions(path="backend/data/substitutions.json"):
    with open(path, "r") as f:
        return json.load(f)


def clean_ingredient_name(name):
    name = name.lower().strip()
    name = re.sub(r"^\d+\s*", "", name)
    name = re.sub(r"^(the|a|an|a package of|a can of|a cup of|package of|can of|cup of)\s+", "", name)
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


def get_substitutions(missing_ingredients, substitutions_map):
    suggestions = {}
    for ing in missing_ingredients:
        if ing in substitutions_map:
            suggestions[ing] = substitutions_map[ing]
    return suggestions


# --- Spoonacular functions (kept for reference; on hold due to account issue) ---

def fetch_recipes(ingredients, api_key, number=5):
    url = "https://api.spoonacular.com/recipes/findByIngredients"
    params = {
        "ingredients": ",".join(ingredients),
        "number": number,
        "apiKey": api_key,
    }
    response = requests.get(url, params=params)
    return response.json()


def fetch_recipes_cached(ingredients, api_key, number=5, cache_file="dev_cache.json"):
    cache_key = ",".join(sorted(ingredients))

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cache = json.load(f)
        if cache_key in cache:
            print("Using cached result")
            return cache[cache_key]
    else:
        cache = {}

    result = fetch_recipes(ingredients, api_key, number)
    cache[cache_key] = result
    with open(cache_file, "w") as f:
        json.dump(cache, f)

    return result


def fetch_recipes_by_cuisine(cuisine, api_key, number=5):
    url = "https://api.spoonacular.com/recipes/complexSearch"
    params = {
        "cuisine": cuisine,
        "number": number,
        "addRecipeInformation": True,
        "apiKey": api_key,
    }
    response = requests.get(url, params=params)
    data = response.json()

    results = []
    for recipe in data.get("results", []):
        results.append({
            "id": recipe["id"],
            "title": recipe["title"],
            "readyInMinutes": recipe.get("readyInMinutes"),
            "servings": recipe.get("servings"),
            "instructions": recipe.get("instructions", "No instructions available."),
        })
    return results


def fetch_recipe_details(recipe_id, api_key):
    url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
    params = {"apiKey": api_key}
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
        "coverage_score": round(coverage_score, 2),
    }


def get_ranked_recipes_final(user_ingredients, api_key, mapping, model, number=10):
    translated = translate_ingredients(user_ingredients, mapping)
    raw_recipes = fetch_recipes(translated, api_key, number=number)
    summaries = [extract_recipe_summary(r) for r in raw_recipes]

    for s in summaries:
        s["semantic_score"] = semantic_recipe_score(user_ingredients, s["used"], s["missed"], model)

    ranked = sorted(
        summaries,
        key=lambda r: (r["coverage_score"], r["semantic_score"]),
        reverse=True,
    )
    return ranked


# --- TheMealDB functions (active) ---

def search_mealdb_by_ingredient(ingredient, api_key="1"):
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/filter.php"
    response = requests.get(url, params={"i": ingredient})
    return response.json().get("meals") or []


def search_mealdb_by_area(area, api_key="1"):
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/filter.php"
    response = requests.get(url, params={"a": area})
    return response.json().get("meals") or []


def fetch_mealdb_details(meal_id, api_key="1"):
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/lookup.php"
    response = requests.get(url, params={"i": meal_id})
    meals = response.json().get("meals")
    return meals[0] if meals else None


def extract_mealdb_ingredients(meal):
    ingredients = []
    for i in range(1, 21):
        ing = meal.get(f"strIngredient{i}", "")
        if ing and ing.strip():
            ingredients.append(clean_ingredient_name(ing))
    return ingredients


# Items assumed to be in every kitchen; excluded from coverage scoring
STAPLES = {
    "salt", "pepper", "black pepper", "water",
    "oil", "vegetable oil", "olive oil", "sunflower oil", "cooking oil",
}


def extract_mealdb_ingredients(meal):
    ingredients = []
    for i in range(1, 21):
        ing = meal.get(f"strIngredient{i}") or ""
        if ing.strip():
            cleaned = clean_ingredient_name(ing)
            if cleaned and cleaned not in ingredients:   # dedupe, keep order
                ingredients.append(cleaned)
    return ingredients


def get_mealdb_summary(meal, user_ingredients):
    used, missed, staples = [], [], []

    for meal_ing in extract_mealdb_ingredients(meal):
        if meal_ing in STAPLES:
            staples.append(meal_ing)
            continue
        if any(u in meal_ing or meal_ing in u for u in user_ingredients):
            used.append(meal_ing)
        else:
            missed.append(meal_ing)

    total = len(used) + len(missed)          # staples excluded
    coverage_score = len(used) / total if total > 0 else 0

    matched_user = sum(
    1 for u in user_ingredients
    if any(u in m or m in u for m in used)
    )

    return {
        "id": meal["idMeal"],
        "title": meal["strMeal"],
        "image": meal.get("strMealThumb", ""),      # new
        "used": used,
        "missed": missed,
        "staples": staples,
        "matched_user": matched_user,
        "coverage_score": round(coverage_score, 2),
        "instructions": meal.get("strInstructions", ""),
    }


def get_ranked_mealdb_recipes(user_ingredients, number=10, mapping=None):
    # Clean input
    user_ingredients = [i.strip().lower() for i in user_ingredients if i and i.strip()]
    if not user_ingredients:
        return []

    # Apply Indian -> Western translation layer
    if mapping is None:
        try:
            mapping = load_ingredient_mapping()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[mapping] not loaded, skipping translation: {e}")
            mapping = {}
    if mapping:
        user_ingredients = translate_ingredients(user_ingredients, mapping)

    # Search MealDB with EVERY ingredient; count how many ingredients hit each recipe
    hits = {}
    for ing in user_ingredients:
        for c in search_mealdb_by_ingredient(ing.replace(" ", "_")):
            hits[c["idMeal"]] = hits.get(c["idMeal"], 0) + 1

    if not hits:
        return []

    top_ids = sorted(hits, key=hits.get, reverse=True)[:number]

    results = []
    for meal_id in top_ids:
        meal = fetch_mealdb_details(meal_id)
        if meal:
            results.append(get_mealdb_summary(meal, user_ingredients))

    main = user_ingredients[0]
    return sorted(
        results,
        key=lambda r: (
            any(main in u or u in main for u in r["used"]),   # contains the main ingredient
            r["matched_user"],
            r["coverage_score"],
        ),
        reverse=True,
    )

AREA_ALIASES = {"indian": "India"}   # MealDB's recipe records use "India", not "Indian"


def get_cuisine_recipes(cuisine, number=10):
    area = AREA_ALIASES.get(cuisine.strip().lower(), cuisine)
    candidates = search_mealdb_by_area(area)

    if not candidates and area != cuisine:
        candidates = search_mealdb_by_area(cuisine)

    if not candidates:
        return []

    results = []
    for c in candidates[:number]:
        meal = fetch_mealdb_details(c["idMeal"])
        if meal:
            results.append({
                "id": meal["idMeal"],
                "title": meal["strMeal"],
                "instructions": meal.get("strInstructions", ""),
                "ingredients": extract_mealdb_ingredients(meal),
            })

    return results

# --- Semantic scoring ---

def semantic_recipe_score(user_ingredients, recipe_used, recipe_missed, model):
    user_text = ", ".join(user_ingredients)
    recipe_text = ", ".join(recipe_used + recipe_missed)

    user_embedding = model.encode(user_text)
    recipe_embedding = model.encode(recipe_text)

    score = util.cos_sim(user_embedding, recipe_embedding).item()
    return round(score, 3)


# --- Gemini intent parsing ---

MEALDB_AREAS = [
    "American", "British", "Canadian", "Chinese", "Croatian", "Dutch", "Egyptian",
    "Filipino", "French", "Greek", "Indian", "Irish", "Italian", "Jamaican",
    "Japanese", "Kenyan", "Malaysian", "Mexican", "Moroccan", "Polish",
    "Portuguese", "Russian", "Spanish", "Thai", "Tunisian", "Turkish",
    "Ukrainian", "Vietnamese",
]


def fallback_parse_intent(message: str):
    """Rule-based parser used when Gemini is unavailable."""
    text = message.lower()

    for area in MEALDB_AREAS:
        if area.lower() in text:
            return {"intent": "cuisine_search", "cuisine": area}

    m = re.search(
        r"(?:i have|i've got|i got|have|got|with|using)\s+(.+?)"
        r"(?:[,.]?\s*(?:what|which|how|can|could|any)\b|[?.!]|$)",
        text,
    )
    if m:
        parts = re.split(r",|\band\b|&", m.group(1))
        ingredients = [p.strip() for p in parts if p.strip()]
        if ingredients:
            return {"intent": "ingredient_search", "ingredients": ingredients}

    return None


def parse_user_intent(user_message: str, gemini_api_key: str, retries: int = 3) -> dict:
    client = genai.Client(api_key=gemini_api_key)

    prompt = f"""You are an intent parser for a cooking assistant. Extract structured JSON based on the user's message.

1. If the user lists ingredients they have:
{{"intent": "ingredient_search", "ingredients": ["chicken", "rice", "onions"]}}

2. If the user asks for a specific cuisine:
{{"intent": "cuisine_search", "cuisine": "Italian"}}

User message: "{user_message}"
"""

    models_to_try = [
        m for m in (
            os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            os.getenv("GEMINI_FALLBACK_MODEL"),   # optional second model
        ) if m
    ]

    for model_name in models_to_try:
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                )
                if not response.text:
                    print(f"[intent] {model_name}: empty response")
                    break

                parsed = json.loads(response.text.strip())
                if isinstance(parsed, list):
                    parsed = parsed[0] if parsed else {}
                if isinstance(parsed, dict) and "intent" in parsed:
                    return parsed
                break

            except APIError as e:
                code = getattr(e, "code", None)
                print(f"[intent] {model_name}: APIError code={code} (attempt {attempt + 1}/{retries})")
                if code in (429, 500, 503):
                    time.sleep(2 ** attempt)      # 1s, 2s, 4s
                    continue                      # retry same model
                break                             # 404/400/403: try next model
            except Exception as e:
                print(f"[intent] {model_name}: {type(e).__name__}: {e}")
                if isinstance(e, (httpx.TransportError, httpx.TimeoutException)):
                    time.sleep(2 ** attempt)
                    continue                      # transient network error: retry
                break                             # anything else (e.g. bad JSON): stop

    # Gemini unavailable: use the local rule-based parser
    fallback = fallback_parse_intent(user_message)
    if fallback:
        print("[intent] using local fallback parser")
        return fallback

    return {"intent": "unknown", "raw_message": user_message}
# --- Chat handler ---

def handle_chat_message(user_message, gemini_api_key):
    intent_data = parse_user_intent(user_message, gemini_api_key)
    intent = intent_data.get("intent")

    if intent == "ingredient_search":
        ingredients = intent_data.get("ingredients", [])
        results = get_ranked_mealdb_recipes(ingredients) if ingredients else []
        return {"type": "ingredient_search", "ingredients": ingredients, "results": results}

    elif intent == "cuisine_search":
        cuisine = intent_data.get("cuisine", "")
        results = get_cuisine_recipes(cuisine) if cuisine else []
        return {"type": "cuisine_search", "cuisine": cuisine, "results": results}

    return {"type": "unknown", "results": []}