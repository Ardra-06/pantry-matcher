# Pantry Matcher

Find recipes you can cook right now, using ingredients you already have.

## The Problem

Most recipe apps start from a dish and send you shopping. Pantry Matcher starts from your kitchen: you list what you have, and it ranks recipes by how much of each one you already own, suggests substitutes for what's missing, and shows full instructions on demand.

<img width="1609" height="860" alt="AdobeExpressPhotos_3bd73460e568416e9d6d3c942f0e8e8e_CopyEdited" src="https://github.com/user-attachments/assets/b4d33600-4eae-4e37-a83a-a0c3e0aa59e9" />

## Features

- Ingredient search, ranked by how many of your ingredients each recipe uses
- Indian-to-Western ingredient translation layer (e.g. `curd` → `yogurt`, `capsicum` → `bell pepper`)
- Substitution suggestions for missing ingredients
- Chat endpoint: write a plain-English message and Gemini works out whether you listed ingredients or asked for a cuisine
- Full recipe details (ingredients and instructions) on demand

## Key Design Decisions

**Indian ingredient translation layer.** Recipe APIs use a Western-centric ingredient vocabulary. While building on Spoonacular, searching "curd" returned irrelevant matches such as tofu. I added a hand-curated dictionary mapping common Indian ingredient names to Western equivalents, with RapidFuzz fuzzy matching as a fallback for typos and spelling variants.

**Embeddings: tested and scoped out of ingredient matching.** I tried sentence embeddings (`all-MiniLM-L6-v2`) for ingredient-level synonym matching. In my tests, general-purpose embeddings captured topical closeness rather than ingredient identity: "onion" and "garlic" scored closer than "curd" and "yogurt", even though the second pair is the same food. So matching uses the dictionary first and fuzzy matching second. A recipe-level embedding tie-breaker exists in the Spoonacular code path but is not used by the current TheMealDB ranking.

**Ranking.** Staples (salt, pepper, water, common oils) are excluded from scoring so they don't count as "missing". Matching is word-based, so "chicken stock cube" does not count as chicken. Recipes are ordered by whether they contain your main (first-listed) ingredient, then by how many of your ingredients they match, then by coverage (the share of the recipe's non-staple ingredients you have).

**Resilient intent parsing.** `/chat` calls Gemini with retries and exponential backoff on rate-limit, server and network errors. If Gemini stays unavailable, a rule-based parser handles common phrasings ("I have X, Y and Z", cuisine names).

**Data-source quirk handled.** TheMealDB lists the cuisine as `Indian` in its area list but labels the recipes `India`, so filtering by `Indian` returns nothing. An alias map in the code fixes this.

## Architecture

```
Frontend (HTML/JS)
        ↓
FastAPI backend
        ↓
Ingredient translation (dictionary + fuzzy matching)
        ↓
TheMealDB (recipe source)
        ↓
Staple filtering + ranking
        ↓
Substitution suggestions
        ↓
Ranked results + on-demand recipe details
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /recipes` | Body: `{"ingredients": ["chicken", "carrots"]}`. Returns ranked recipes with `used`, `missed`, `coverage_score` and `substitutions`. |
| `GET /recipes/{recipe_id}` | Ingredients and instructions for one recipe. |
| `POST /chat` | Body: `{"message": "I have chicken and rice, what can I make?"}`. Gemini-parsed ingredient or cuisine search. |

## Tech Stack

- **Backend:** Python, FastAPI
- **Matching:** RapidFuzz, word-based ingredient matching
- **LLM:** Google Gemini (intent parsing for `/chat`)
- **Data:** TheMealDB (no API key required)
- **Frontend:** HTML, vanilla JavaScript
- **Inactive:** Spoonacular functions and sentence-transformers scoring remain in `ingredients.py` but the current app doesn't call them

## Running Locally

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Create `api.env` in the project root (only needed for `/chat`):
   ```
   GEMINI_API_KEY=your_key_here
   ```
   Optionally set `GEMINI_MODEL` to override the default model name.
3. Start the backend from the project root:
   ```
   python -m uvicorn backend.app.main:app --reload
   ```
4. Open `frontend/index.html` in your browser.

## Limitations

- TheMealDB is small and Western-leaning. It has some Indian recipes (Dal fry, Baingan Bharta, Lamb Biryani and others), but far fewer than a dedicated Indian recipe source would. This is the main limit on result quality.
- TheMealDB provides no cooking time or servings.
- Ingredient matching is word-based, so unusual phrasings can miss.
- The web page uses `/recipes`. `/chat` is available through the API but isn't wired into the UI yet.
- Ranking quality hasn't been formally evaluated.
- Each search makes roughly 15 external API calls and has no caching, so responses take a few seconds.

## Future Enhancements

- Evaluate ranking on a fixed set of test queries
- Re-add embeddings as a tie-breaker and measure whether they help
- Add a dedicated Indian recipe source to improve coverage
- Cache API calls
- Nutrition analysis against dietary goals
- Photo-based ingredient recognition
- Multi-user pantry sync
