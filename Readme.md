# Pantry Matcher

Find recipes you can actually cook right now, using ingredients you already have.

## The Problem

Most recipe apps assume you'll shop for a specific dish. Pantry Matcher flips that — you tell it what's in your kitchen, and it ranks real recipes by how many ingredients you already have, suggests substitutes for what's missing, and shows full cooking instructions on demand.

## Key Design Decisions

**Indian ingredient translation layer.** The underlying recipe API (Spoonacular) has a Western-centric ingredient database — searching "curd" returned irrelevant matches like tofu. Rather than accept this limitation, I built a translation layer mapping common Indian ingredient names to their closest Western equivalents, with fuzzy string matching (via RapidFuzz) as a fallback to catch typos and spelling variants.

**Embeddings: tested, and honestly scoped.** I initially planned to use sentence embeddings (`all-MiniLM-L6-v2`) for ingredient-level synonym matching (e.g. recognizing "capsicum" ≈ "bell pepper" automatically). Empirical testing revealed a real limitation: general-purpose embeddings capture topical closeness, not ingredient-identity — "onion" and "garlic" scored *higher* in similarity than "curd" and "yogurt," despite the latter pair being the same food.

Rather than force embeddings into a role they weren't suited for, I redesigned the matching system as a hybrid:
- **Dictionary lookup** (primary) — hand-curated, precise translations
- **Fuzzy string matching** (secondary) — catches typos/spelling variants
- **Embeddings** (repurposed) — used at the whole-recipe level as a coverage-score tie-breaker, where they proved to add real, measurable value

This is a deliberate example of testing a technique, measuring its actual contribution, and scoping it appropriately rather than using it because it sounds impressive.

## Architecture

Frontend (HTML/JS)
↓
FastAPI backend
↓
Ingredient translation (dictionary + fuzzy matching)
↓
Spoonacular API (recipe corpus)
↓
Coverage scoring + semantic tie-breaking
↓
Substitution suggestions
↓
Ranked results + on-demand full recipe details


## Tech Stack

- **Backend:** FastAPI, Python
- **ML/NLP:** sentence-transformers (MiniLM), RapidFuzz
- **Frontend:** HTML, vanilla JavaScript
- **External API:** Spoonacular

## Running Locally

1. Clone the repo and install dependencies:

pip install fastapi uvicorn requests python-dotenv sentence-transformers rapidfuzz


2. Get a free Spoonacular API key at [spoonacular.com/food-api](https://spoonacular.com/food-api)

3. Create `api.env` in the project root:

SPOONACULAR_API_KEY=your_key_here

4. Start the backend:

python -m uvicorn backend.app.main:app --reload


5. Open `frontend/index.html` in your browser

## Future Enhancements

- Nutrition analysis matched to health/dietary goals
- Photo-based ingredient recognition (computer vision)
- Budget-aware recommendations
- Multi-user pantry sync