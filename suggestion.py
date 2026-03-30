from flask import Flask, request, jsonify
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import MultiLabelBinarizer
import pandas as pd
from datetime import datetime, timedelta
import json
import random

# Helper: Get random cities
def get_random_cities(n=5):
    cities = ["New York", "Los Angeles", "Tokyo", "London", "Paris", "Dubai", "Rome", "Bangkok", "Sydney", "Toronto"]
    return random.sample(cities, n)

def packages_cities(n=5):
    cities = ["Sweden", "Norway", "Finland", "Denmark", "Iceland","Goa","Bali"]
    return random.sample(cities, n)

# Generate dynamic date ranges
def get_date_range(days_ahead=5, start_offset=3):
    today = datetime.today()
    return [
        (today + timedelta(days=offset)).strftime("%b %d")
        for offset in range(start_offset, start_offset + days_ahead)
    ]

# Currency-specific city mapping
currency_city_map = {
    "inr": ["Delhi", "Mumbai", "Bangalore", "Hyderabad", "Chennai"],
    "usd": ["New York", "Los Angeles", "Chicago", "San Francisco", "Seattle"]
}

# Currency-specific price generation
def generate_price(currency):
    currency = currency.lower()
    standard_prices = {
        "inr": ["₹15000", "₹25000", "₹30000", "₹35000"],
        "usd": ["$200", "$250", "$300", "$350"]
    }
    return standard_prices.get(currency, ["N/A"])

# Prepare date ranges
date_range1 = get_date_range(days_ahead=8, start_offset=3)
date_range2 = get_date_range(days_ahead=8, start_offset=11)
date_range_default = get_date_range()
random_cities = get_random_cities()
packages_city_sample = packages_cities()

# Load and process suggestion.json
with open("suggestion.json", "r") as file:
    data = json.load(file)

for item in data:
    if "slot_value" in item:
        if item["slot_value"] == ["date_range1"]:
            item["slot_value"] = date_range1
        elif item["slot_value"] == ["date_range2"]:
            item["slot_value"] =["date_range2"]
        elif item["slot_value"] == ["city"]:
            item["slot_value"] = ["city"]  # Marker for dynamic city generation
        elif item["slot_value"] == ["packages_cities"]:
            item["slot_value"] = packages_city_sample
        elif item["slot_value"] == ["price"]:
            item["slot_value"] = ["price"]  # Marker for dynamic price

# Convert to DataFrame
df = pd.DataFrame(data)
X = df["query"]
y = df["slot_value"]

# Encode slot values
mlb = MultiLabelBinarizer()
y_encoded = mlb.fit_transform(y)

# Build and train model
model = make_pipeline(CountVectorizer(), MultiOutputClassifier(RandomForestClassifier()))
model.fit(X, y_encoded)
import dateparser
from datetime import datetime, timedelta

def get_future_dates_after(previous_date: str, offset_days: int = 1, count: int = 5):
    """
    Given a previous_date in any common format, return `count` dates after `previous_date + offset_days`.
    
    Args:
        previous_date (str): The reference date (any common string format).
        offset_days (int): Number of days to skip after the previous date (e.g., +5).
        count (int): Number of future dates to return.
    
    Returns:
        List[str]: Dates in format 'Jun 24', 'Jun 25', ...
    """
    # Try parsing the date using dateparser
    parsed_date = dateparser.parse(previous_date)

    if not parsed_date:
        raise ValueError(f"Could not parse date: {previous_date}")

    start_date = parsed_date + timedelta(days=offset_days)
    return [
        (start_date + timedelta(days=i)).strftime("%b %d")
        for i in range(count)
    ]

# Generate suggestions based on query and currency
def generate_user_input_suggestions(query, currency,previous_date):
    prediction = model.predict([query])
    decoded = mlb.inverse_transform(prediction)
    suggestions = []
    default_suggestions=["Book a Flight","Book a Hotel","Book a package","Book an Attraction"]
    if not decoded[0]:
        return default_suggestions
    for item in decoded[0]:
        if item == "city":
            available_cities = [city for city in currency_city_map.get(currency.lower(), []) if city.lower() != previous_date.lower()]
            suggestions.extend(random.sample(available_cities, min(3, len(available_cities))))
        elif item == "price":
            suggestions.extend(generate_price(currency))
        elif item=="date_range2" and previous_date:
            suggestions.extend(get_future_dates_after(previous_date,offset_days=8))
        elif item == "date_range1":
            suggestions.extend(date_range2)
        else:
            suggestions.append(item)

    return suggestions

