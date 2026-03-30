import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
import string
from datetime import datetime, timedelta,date
import requests
import re
import json
import openai
from math import radians, sin, cos, sqrt, atan2
from datetime import date, timedelta
from decouple import config
from flask import Flask, request, jsonify
from geopy.distance import geodesic
import requests
from sklearn.metrics.pairwise import cosine_similarity
api_key = config('openai')
openai.api_key = api_key


# Initialize global variables and objects
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))




def find_code(city,currency):
    base_url=config('ATTRACTIONS_CODE')
    url = base_url.format(city,currency)
    response = requests.get(url)
    if response.status_code == 200:
        result = response.json()
        if 'data' in result:
            destination_info = result['data'].get('destination', [])
            if destination_info:
                first_destination_id = destination_info[0].get('id', None)
                city_name = destination_info[0].get('name', None)
                print(first_destination_id, city_name)
                return first_destination_id, city_name         
    return None, None




def preprocess_text(text):
    tokens = word_tokenize(text.lower())
    processed_tokens = [lemmatizer.lemmatize(token) for token in tokens if token not in stop_words and token not in string.punctuation]
    return ' '.join(processed_tokens)




def generate_google_maps_link(attractions):
    base_url = "https://www.google.com/maps/dir/"
    
    locations = []
    for attraction in attractions:
        if isinstance(attraction, pd.Series):  # Convert Series to dictionary
            attraction = attraction.to_dict()

        if isinstance(attraction, dict):  # Ensure it's a dictionary before accessing keys
            lat = attraction.get('latitude')
            lng = attraction.get('longitude')
           # print("lat long :",lat,lng)

            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):  # Ensure lat/lng are valid
                locations.append(f"{lat},{lng}")

    return base_url + "/".join(locations) if locations else "N/A"


WEIGHTS = {"preference": 0.4, "popularity": 0.4, "proximity": 0.2}

def normalize(value, min_val, max_val):
    return (value - min_val) / (max_val - min_val) if max_val > min_val else 0

# Function to classify attraction category

def search_attractions_n(attraction_data, keyword):
    attraction_names = [attraction["category"] for attraction in attraction_data]
    
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(attraction_names)
    keyword_vector = vectorizer.transform([keyword])
    
    cosine_similarities = cosine_similarity(tfidf_matrix, keyword_vector).flatten()
    
    min_popularity = min(a["score"] for a in attraction_data)
    max_popularity = max(a["score"] for a in attraction_data)
    
    min_similarity = min(cosine_similarities)
    max_similarity = max(cosine_similarities)
    
    for i, attraction in enumerate(attraction_data):
        attraction["cosine_similarity"] = normalize(cosine_similarities[i], min_similarity, max_similarity)
        attraction["popularity_score"] = normalize(attraction["score"], min_popularity, max_popularity)
        attraction["final_score"] = (
            WEIGHTS["preference"] * attraction["cosine_similarity"] +
            WEIGHTS["popularity"] * attraction["popularity_score"]
        )
    
    return sorted(attraction_data, key=lambda x: x["final_score"], reverse=True)

def get_nearby_restaurants(LAT,LNG):
    API_KEY = config('google_key')
    # Coordinates (Example: New York City)
    #LAT, LNG = 40.730610, -73.935242

    # Google Places API Endpoint
    url = config('google_api')

    # API Parameters
    params = {
    "location": f"{LAT},{LNG}",
    "radius": 2000,  # 2km range
    "type": "restaurant",
    "key": API_KEY
}

    # Make Request
    response = requests.get(url, params=params)
    data = response.json()

    # Extract Results
    restaurants = []
    for place in data.get("results", []):
        restaurant = {
        "name": place["name"],
        "rating": place.get("rating", "N/A"),
        "address": place.get("vicinity", "Address not available"),
        "latitude": place["geometry"]["location"]["lat"],
        "longitude": place["geometry"]["location"]["lng"]
        }
        restaurants.append(restaurant)

    return restaurants
# Assign nearby attractions using Haversine formula



def generate_trip_summary_n(attractions):
    """Generates a 4-line attractive trip summary without mentioning days."""
    attraction_list = ", ".join(attractions)
    prompt = (
        f"Create an engaging 7-line trip summary (10 words per line) "
        f"about exploring {attraction_list}. Highlight excitement and adventure."
    )
    return generate_description_n(prompt)

def generate_description_n(prompt):
    """Calls OpenAI API to generate descriptions."""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "You are a travel writer."},
                  {"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response["choices"][0]["message"]["content"]

def generate_daily_trip_description_n(attractions):
    """Generates a 5-line description for a day's trip."""
    attraction_names = ", ".join(attractions)
    prompt = (
        f"Write a 3-line summary (10 words per line) "
        f"for a day visiting {attraction_names}."
    )
    return generate_description_n(prompt)

def generate_attraction_description_n(attraction_name):
    """Generates a 4-line description for an individual attraction."""
    prompt = (
        f"Write a description around 100 characters"
        f"about {attraction_name}."
    )
    return generate_description_n(prompt)



import openai
import requests
def classify_attractions_new(attraction_names):
    """Classify multiple attractions in one API call."""
    prompt = f"""Classify the following attractions into one of these categories:
    - Sightseeing
    - Iconic Landmarks
    - Adventure & outdoors
    - Art & Museums
    - Culture & Heritage
    - Family &  Fun

    Provide the category for each attraction in the format:
    Attraction: <name> -> Category: <category>

    Attractions:
    """ + "\n".join(f"- {name}" for name in attraction_names)

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an expert in categorizing tourist attractions."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200,
        temperature=0
    )

    response_text = response["choices"][0]["message"]["content"].strip()
    
    # Parse the response to extract categories
    categories = {}
    for line in response_text.split("\n"):
        if "-> Category:" in line:
            parts = line.split("-> Category:")
            attraction_name = parts[0].replace("Attraction:", "").strip()
            category = parts[1].strip()
            categories[attraction_name] = category

    return categories  # Returns a dictionary of {attraction_name: category}


def get_all_attractions_lat_long_new(city_id, user_preference_keyword, max_calls=2):
    """Fetch attractions and classify them efficiently."""
    url = config('destinations_attraction')
    extracted_data = []
    all_attractions = []
    start = 1
    count = 30
    calls = 0

    while calls < max_calls:
        payload = {
            "destinationId": city_id,
            "sorting": {"sort": "DEFAULT"},
            "pagination": {"start": start, "count": count}
        }
        headers = {"Content-Type": "application/json"}

        response = requests.post(url, json=payload, headers=headers)
        

        if response.status_code == 200:
            data = response.json().get('data', {})
            attractions = data.get("attractions", [])

            if not attractions:
                print("No more attractions found, stopping further API calls.")
                break  # Stop calling if no more attractions are returned

            all_attractions.extend(attractions)  # Store all attractions from API calls
            
            start += count  # Increment pagination start value
        else:
            print(f"API Error: {response.status_code}")
            break
        
        calls += 1

    print(f"Total Attractions Fetched: {len(all_attractions)}")

    if not all_attractions:
        print("No attractions found, returning empty result.")
        return []

    # Classify attractions in batch
    attraction_names = [attraction.get("name") for attraction in all_attractions]
    categories = classify_attractions_new(attraction_names)

    # Process attractions based on the "primary" destination condition
    filtered_data = []
    
    for attraction in all_attractions:
        if any(dest["id"] == city_id and dest.get("primary", False) for dest in attraction.get("destinations", [])):
            name = attraction.get("name")
            productCodes = attraction.get("productCodes")
            category = categories.get(name, "Unknown")
            total_reviews = attraction.get("reviews", {}).get("totalReviews", 0)
            rating = attraction.get("reviews", {}).get("combinedAverageRating", 0)
            weighted_score = (total_reviews + rating * 10)
            images = attraction.get("images", [])
            first_image_url = images[0]["url"] if images else None

            filtered_data.append({
                "id": attraction.get("attractionId"),
                "productCodes": productCodes,
                "name": name,
                "url": attraction.get("attractionUrl"),
                "total_reviews": total_reviews,
                "average_rating": rating,
                "latitude": attraction.get("center", {}).get("latitude"),
                "longitude": attraction.get("center", {}).get("longitude"),
                "category": category,
                "score": weighted_score,
                "image_url": first_image_url
            })

    print(f"Filtered Attractions (Primary=True): {len(filtered_data)}")

    # If filtered attractions are less than 5, use all attractions instead
    if len(filtered_data) < 5:
        print("Less than 5 primary attractions found, including all attractions...")
        filtered_data = []
        for attraction in all_attractions:
            name = attraction.get("name")
            productCodes = attraction.get("productCodes")
            category = categories.get(name, "Unknown")
            total_reviews = attraction.get("reviews", {}).get("totalReviews", 0)
            rating = attraction.get("reviews", {}).get("combinedAverageRating", 0)
            weighted_score = (total_reviews + rating * 10)
            images = attraction.get("images", [])
            first_image_url = images[0]["url"] if images else None

            filtered_data.append({
                "id": attraction.get("attractionId"),
                "productCodes": productCodes,
                "name": name,
                "url": attraction.get("attractionUrl"),
                "total_reviews": total_reviews,
                "average_rating": rating,
                "latitude": attraction.get("center", {}).get("latitude"),
                "longitude": attraction.get("center", {}).get("longitude"),
                "category": category,
                "score": weighted_score,
                "image_url": first_image_url
            })

    print(f"Final Attractions Count: {len(filtered_data)}")

    # Process user preference sorting
    attraction_data = search_attractions_n(filtered_data, user_preference_keyword)
    return attraction_data

import concurrent.futures
from geopy.distance import geodesic

WEIGHTS = {
    "preference": 0.4,
    "popularity": 0.3,
    "proximity": 0.3
}

import concurrent.futures
from geopy.distance import geodesic

def assign_nearby_attractions_new(attractions, num_days, city_name):
    assigned_days = {}
    remaining_attractions = attractions[:]
    all_attractions = []
    max_distance = 50  # km

    for day in range(1, num_days + 1):
        if not remaining_attractions:
            break

        found_pair = False

        for i, first_attraction in enumerate(remaining_attractions):
            second_attraction = None
            min_distance_found = float('inf')

            for j, attraction in enumerate(remaining_attractions):
                if i == j:
                    continue
                distance = geodesic(
                    (first_attraction["latitude"], first_attraction["longitude"]),
                    (attraction["latitude"], attraction["longitude"])
                ).kilometers

                if distance <= max_distance and distance < min_distance_found:
                    min_distance_found = distance
                    second_attraction = (j, attraction)

            if second_attraction:
                idx_second, attraction_obj = second_attraction

                # Select attractions
                daily_attractions = [first_attraction, attraction_obj]
                found_pair = True

                # Use concurrent futures to get data in parallel
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_maps_link = executor.submit(generate_google_maps_link, daily_attractions)
                    future_day_description = executor.submit(generate_daily_trip_description_n, [a["name"] for a in daily_attractions])
                    #future_restaurants = executor.submit(get_nearby_restaurants, first_attraction["latitude"], first_attraction["longitude"])
                    future_descriptions = {
                        a["name"]: executor.submit(generate_attraction_description_n, f"{a['name']}+{city_name}")
                        for a in daily_attractions
                    }

                    # Collect results
                    google_maps_link = future_maps_link.result()
                    day_description = future_day_description.result()
                   # restaurants = future_restaurants.result()
                    for attraction in daily_attractions:
                        attraction["description"] = future_descriptions[attraction["name"]].result()
                        all_attractions.append(attraction["name"])

                # Assign to the day
                assigned_days[f"Day {day}"] = {
                    "attractions": daily_attractions,
                    "google_maps_link": google_maps_link,
                    "day_description": day_description,
                    "restaurants_for_the_day": "restaurants"
                }

                # Remove selected attractions
                for idx in sorted([i, idx_second], reverse=True):
                    del remaining_attractions[idx]

                break  # Move to the next day after assigning a pair

        if not found_pair:
            break

    # Trip summary at the end
    trip_summary = generate_trip_summary_n(all_attractions)
    return assigned_days, remaining_attractions, trip_summary

def generate_gpt4_trip_plan(city, num_days, keyword):
    prompt = f"""
Create a {num_days}-day travel itinerary for {city} based on the preference: "{keyword}".

OUTPUT RULES:
- Respond ONLY with valid JSON.
- NO explanation, NO text outside JSON.
- Use the exact structure provided below.
- Every attraction MUST include latitude and longitude (approximate is OK).
- "image_url" may be "" (empty string).
- 2 attractions per day.

STRUCTURE TO FOLLOW EXACTLY:

{{
  "Day 1": {{
    "attractions": [
      {{
        "name": "",
        "description": "",
        "latitude": 0.0,
        "longitude": 0.0,
        "image_url": ""
      }},
      {{
        "name": "",
        "description": "",
        "latitude": 0.0,
        "longitude": 0.0,
        "image_url": ""
      }}
    ],
    "google_maps_link": "",
    "day_description": ""
    "restaurants_for_the_day": []
  }}
}}

REQUIREMENTS:
- For each day generate EXACTLY 2 attractions.
- Use realistic coordinates for the city.
- Day description = 1–2 lines.
- Attraction description = max 20 words.
- google_maps_link = Google Maps direction link between the 2 attractions.

Now generate the plan for {num_days} days.
"""

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",   # You can switch to gpt-4.1
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )

    result = response["choices"][0]["message"]["content"]

    # CLEANUP: Remove accidental newlines
    cleaned = result.replace("\\n", " ").replace("\n", " ")
    
    return json.loads(cleaned)

def get_image_url(query):
    params = {"query": query}
    UNSPLASH_API_URL = "https://api.travelfika.com/api/unsplash/search/photos"
    try:
        res = requests.get(UNSPLASH_API_URL, params=params)
        data = res.json()

        # Extract first image
        first_result = data["data"]["results"][4]
        return first_result["urls"]["regular"]

    except:
        return "" 
def complete_itinerary_with_images(city, num_days, keyword):
    itinerary = generate_gpt4_trip_plan(city, num_days, keyword)

    # Loop through all days and both attractions
    for day, content in itinerary.items():
        for attraction in content["attractions"]:
            attraction_name = attraction["name"]

            # Fetch Unsplash image for that attraction
            image_url = get_image_url(attraction_name+" "+city)

            # Insert into structure
            attraction["image_url"] = image_url

    return itinerary



def full_attraction(city,no_of_days,keyword,destinationID,currency):
    #attraction_data=find_attractions_ai(city, no_of_days,currency)
    #city_id, city_name = find_code(city, currency)
    city_id=destinationID
    city_name=city
    attraction_data=get_all_attractions_lat_long_new(city_id,keyword,max_calls=3)
    #relevant_attraction = search_attractions_n(attraction_data, keyword)
    #relevant_attractions = relevant_attraction.sort_values(by='cosine_similarity', ascending=False)
    #schedule,r = generate_schedule(relevant_attractions, checkin_date, checkout_date, keyword=keyword)
    schedule,r,d = assign_nearby_attractions_new(attraction_data,no_of_days,city_name)
    #return  schedule,r,d,city_id,city_name
    if len(attraction_data)< no_of_days*2:
        return complete_itinerary_with_images(city, no_of_days, keyword),r,d,city_id,city_name
        print(complete_itinerary_with_images(city, no_of_days, keyword))
    else:
        return  schedule,r,d,city_id,city_name

    #schedule,r = assign_nearby_attractions_n(relevant_attraction,no_of_days)
    