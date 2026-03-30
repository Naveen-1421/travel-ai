
from datetime import datetime
import requests
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from subclass import suggest_hotels


embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


def get_embeddings(texts):
    if not texts:
        return np.empty((0, embedding_model.get_sentence_embedding_dimension()))

    emb = embedding_model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    if emb.ndim == 1:
        emb = emb.reshape(1, -1)

    return emb

def detect_season(travel_date=None):
    date = travel_date or datetime.now()
    m = date.month

    if m in [11, 12, 1, 2]:
        return "winter"
    if m in [3, 4, 5, 6]:
        return "summer"
    if m in [7, 8, 9]:
        return "monsoon"
    return "autumn"


def detect_season_from_query(query, travel_date=None):
    q = query.lower()
    for s in ["winter", "summer", "monsoon", "autumn"]:
        if s in q:
            return s
    return detect_season(travel_date)

DESTINATION_CLIMATE = {

    "Amritsar": {"best": ["winter", "autumn"], "avoid": ["summer"]},
    "Agra": {"best": ["winter", "autumn"], "avoid": ["summer"]},
    "Delhi": {"best": ["winter", "autumn"], "avoid": ["summer"]},
    "Jaipur": {"best": ["winter"], "avoid": ["summer", "monsoon"]},
    "Jodhpur": {"best": ["winter"], "avoid": ["summer"]},
    "Udaipur": {"best": ["winter"], "avoid": ["summer"]},
    "Jaisalmer": {"best": ["winter"], "avoid": ["summer"]},
    "Pushkar": {"best": ["winter"], "avoid": ["summer"]},
    "Mount Abu": {"best": ["summer", "winter"], "avoid": []},
    "Ranthambore": {"best": ["winter"], "avoid": ["monsoon", "summer"]},
    "Rajasthan": {"best": ["winter"], "avoid": ["summer"]},

    "Manali": {"best": ["winter", "summer"], "avoid": ["monsoon"]},
    "Ladakh": {"best": ["summer"], "avoid": ["winter", "monsoon"]},
    "Kashmir": {"best": ["summer", "winter"], "avoid": ["monsoon"]},
    "Himachal Pradesh": {"best": ["summer", "winter"], "avoid": ["monsoon"]},
    "Sikkim": {"best": ["spring", "summer"], "avoid": ["monsoon"]},
    "Arunachal Pradesh": {"best": ["spring", "summer"], "avoid": ["monsoon"]},

    "Kerala": {"best": ["winter", "monsoon"], "avoid": []},
    "Varkala": {"best": ["winter", "monsoon"], "avoid": []},
    "Karnataka": {"best": ["winter"], "avoid": ["summer"]},

    # 🏖️ Islands & Beaches
    "Goa": {"best": ["winter"], "avoid": ["monsoon"]},
    "Andaman": {"best": ["winter"], "avoid": ["monsoon"]},
    "Port Blair": {"best": ["winter"], "avoid": ["monsoon"]},
    "Havelock": {"best": ["winter"], "avoid": ["monsoon"]},
    "Neil Island": {"best": ["winter"], "avoid": ["monsoon"]},

    "Meghalaya": {"best": ["winter"], "avoid": ["monsoon"]},
    "Guwahati": {"best": ["winter"], "avoid": ["monsoon"]},

    "Uttar Pradesh": {"best": ["winter"], "avoid": ["summer"]},
}

def seasonal_score(pkg, season):
    dest = pkg.get("data", {}).get("destination")
    climate = DESTINATION_CLIMATE.get(dest)
    if not climate:
        return 0.5
    if season in climate["best"]:
        return 1.0
    if season in climate["avoid"]:
        return 0.1
    return 0.5

def build_package_text(pkg):
    d = pkg.get("data", {})
    return f"""
    {d.get('package_name','')}
    {d.get('description','')}
    {d.get('package_type','')}
    {d.get('destination','')}
    honeymoon couple romantic family adventure
    price {d.get('from_price_inr','')}
    """
def tfidf_similarity_ranking(packages, query):
    docs = [build_package_text(p) for p in packages]

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2)
    )

    tfidf = vectorizer.fit_transform(docs + [query])
    query_vec = tfidf[-1]
    pkg_vecs = tfidf[:-1]

    return cosine_similarity(query_vec, pkg_vecs)[0]

def ml_similarity_ranking(packages, query, season):
    texts = [build_package_text(p) for p in packages]

    # Semantic similarity
    pkg_emb = get_embeddings(texts)
    user_emb = get_embeddings([query])
    emb_sims = cosine_similarity(user_emb, pkg_emb)[0]

    # Keyword similarity
    tfidf_sims = tfidf_similarity_ranking(packages, query)

    ranked = []
    for i, pkg in enumerate(packages):
        score = (
            0.5 * emb_sims[i] +
            0.3 * tfidf_sims[i] +
            0.2 * seasonal_score(pkg, season)
        )
        ranked.append((pkg, score))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in ranked]

def budget_filter(packages, budget=None):
    if not budget:
        return packages
    return [
        p for p in packages
        if p.get("data", {}).get("from_price_inr", 10**9) <= budget
    ]

def sort_low_to_high(packages):
    return sorted(
        packages,
        key=lambda p: p.get("data", {}).get("from_price_inr", 10**9)
    )

POPULAR_DESTINATIONS = [
    "Goa", "Manali", "Kerala", "Kashmir",
    "Bali", "Maldives", "Dubai", "Thailand",
    "Miami","Vietnam"
]

def extract_locations(text):
    q = text.lower()
    return [d for d in POPULAR_DESTINATIONS if d.lower() in q]

def find_code(city, currency):
    url = f"https://api.travelfika.com/api/v1/experiences/searchSuggestions/{city}/{currency}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            dest = r.json().get("data", {}).get("destination", [])
            if dest:
                return dest[0]["id"], dest[0]["name"]
    except:
        pass
    return None, None

import requests

def packages_data(text, currency):
    locations = extract_locations(text)

    base_url = "https://www.travelfika.com"
    all_packages = []
    booking_links = {}

    cities = locations if locations else POPULAR_DESTINATIONS
     
    for city in cities:
        # Get city code and formatted name
        city_id, city_name = find_code(city, currency)
        print(city_id, city_name)
        if not city_id:
            continue

        slug = city_name.lower().replace(" ", "-")
        booking_links[city] = f"{base_url}/tours/packages/{slug}-tour-packages-{city_id}"

        # API 1
        url_packages = "https://api.travelfika.com/api/search-packages"
        payload = {"places": city}
        #print(payload)
        response_packages = requests.post(url_packages, json=payload)
        packages1 = response_packages.json().get("packages", []) if response_packages.status_code == 200 else []
    
        # Fetch Attractions
        url = "https://api.travelfika.com/api/custom-entries/tfexpdetails"
        url_attractions = f"{url}/{city}"
        response_attractions = requests.get(url_attractions)
        packages2 = response_attractions.json() if response_attractions.status_code == 200 else []
       # print(packages2)
        # Merge both API packages
        all_packages.extend(packages1 + packages2)
        #print("all_packages:", all_packages)
        #print("packages1:", packages1, "packages2:",packages2)

    return {
        "packages": all_packages,
        "booking_link": booking_links if not locations else list(booking_links.values())[0]
    }


def hard_filter_destination(packages, destination):
    d = destination.lower()
    result = []

    for p in packages:
        data = p.get("data", {})
        
        if "destination" not in data or not data["destination"]:
            data["destination"] = d   # assign manually
        p["data"] = data
        result.append(p)

    #result.append(p)

    return result
def recommend_packages(
    text,
    currency="INR",
    budget=None,
    travel_date=None,
    top_k=5
):
    locations = extract_locations(text)
    destination = locations[0] if locations else None

    season = detect_season_from_query(text, travel_date)

    data = packages_data(text, currency)
    packages = data["packages"]
    booking_link = data["booking_link"]
    #print("Total packages fetched:", len(packages))
    if destination:
        packages = hard_filter_destination(packages, destination)

    if not packages:
        return [], booking_link

    ranked = ml_similarity_ranking(packages, text, season)
    ranked = budget_filter(ranked, budget)
    ranked = sort_low_to_high(ranked)


    hotels = suggest_hotels(destination, currency)

    return {
        "packages": ranked[:top_k],
        "hotels": hotels,
        "booking_link": booking_link
    }