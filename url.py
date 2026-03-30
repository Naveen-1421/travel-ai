from os import name
import re
import json
import urllib.parse
from typing import List, Dict
import requests
from urllib.parse import quote_plus, quote
import spacy
# ---------------------------
# SEO SLUG (Travelfika style)
# ---------------------------
def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.title()


# ---------------------------
# ROOM PAYLOAD ENCODER
# ---------------------------
def encode_rooms_payload(rooms: int, adults: int, children: int) -> str:
    payload = [{
        "rooms": rooms,
        "adults": adults,
        "children": children,
        "paxes": []
    }]

    # Compact JSON + URL encode
    json_str = json.dumps(payload, separators=(",", ":"))
    return urllib.parse.quote(json_str)

# ---------------------------
# TRAVELFIKA HOTEL DETAIL URL
# ---------------------------
def build_travelfika_booking_url(
    hotel_name,
    hotel_code,
    city_code,
    city_name,
    country,
    rooms,
    adults,
    children,
    checkin_date,
    checkout_date
):

    if not all([hotel_name, hotel_code, city_code, city_name, country, checkin_date, checkout_date]):
        return None  # ❗ skip broken hotels safely

    BASE_URL = "https://www.travelfika.com"

    hotel_slug = f"{slugify(city_name)}-Hotels-{slugify(hotel_name)}"
    room_payload = encode_rooms_payload(rooms, adults, children)
    year = checkin_date.split("-")[0]

    city_segment = f"{city_code},{slugify(city_name)},{slugify(country)}"

    return (
        f"{BASE_URL}/hotel/"
        f"{hotel_slug}/"
        f"{hotel_code}/"
        f"{city_segment}/"
        f"{room_payload}/"
        f"{rooms}/{children}/"
        f"{year}/"
        f"{checkin_date}/"
        f"{checkout_date}"
    )

# ---------------------------
# NORMALIZE HOTEL API DATA
# ---------------------------
def normalize_hotels(api_response):

    # 🔁 Accept both list and dict
    if isinstance(api_response, dict):
        hotels_data = (
            api_response.get("data")
            or api_response.get("responses")
            or []
        )
    elif isinstance(api_response, list):
        hotels_data = api_response
    else:
        raise TypeError(f"Expected dict or list, got {type(api_response)}")

    hotels = []

    for h in hotels_data:
        booking_url = build_travelfika_booking_url(
            hotel_name=h.get("Name"),
            hotel_code=h.get("code"),
            city_code=h.get("city_code"),
            city_name=h.get("city_name"),
            country=h.get("state"),
            rooms=h.get("no_of_room", 1),
            adults=2,
            children=0,
            checkin_date=h.get("checkin_date"),
            checkout_date=h.get("checkout_date"),
        )

        hotels.append({
            "hotel_id": h.get("code"),
            "Name": h.get("Name"),
            "ADDRESS": h.get("ADDRESS"),
            "city_name": h.get("city_name"),
            "city_code": h.get("city_code"),
            "state": h.get("state"),
            "Rating": h.get("Rating"),
            "Price": h.get("Price"),
            "Imageurl": h.get("Imageurl"),
            "checkin_date": h.get("checkin_date"),
            "checkout_date": h.get("checkout_date"),
            "no_of_room": h.get("no_of_room", 1),
            "latitude": h.get("latitude", "N/A"),
            "longitude": h.get("longitude", "N/A"),
            "booking_url": booking_url,
        })
    return hotels

import re

def highlight_headings(text):
    text = re.sub(r'([A-Z][a-zA-Z\s]+):', r'<b>\1:</b>', text)
    return text
user_sessions = {}

nlp = spacy.load("en_core_web_sm")

def find_code(city, currency="INR"):
    """Get Travelfika destination ID and name for a given city."""
    base_url = "https://api.travelfika.com/api/v1/experiences/searchSuggestions/{}/{}"
    url = base_url.format(quote_plus(city), currency)

    try:
        response = requests.get(url)
        if response.status_code == 200:
            result = response.json()
            if "data" in result:
                destination_info = result["data"].get("destination", [])
                if destination_info:
                    first_destination_id = destination_info[0].get("id")
                    city_name = destination_info[0].get("name")
                    return first_destination_id, city_name
        return None, None
    except Exception as e:
        print(f"Error fetching destination for {city}: {e}")
        return None, None


def get_travelfika_urls(keyword, currency="INR"):
    """Fetch Travelfika product URLs for an attraction or keyword."""
    url = f"https://api.travelfika.com/api/v1/experiences/searchSuggestions/{quote_plus(keyword)}/{currency}"
    urls = []

    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json().get("data", {})
            products = data.get("product", [])

            for p in products:
                name_slug = (
                    p.get("name", "").lower().replace(" ", "-").replace(":", "")
                )
                dest_id = p.get("destinationId")
                prod_id = p.get("id")
                travelfika_url = (
                    f"https://www.travelfika.com/tours/{name_slug}/packages/{dest_id}-{prod_id}"
                )
                urls.append(travelfika_url)
        return urls
    except Exception as e:
        print(f"Error fetching product URLs for {keyword}: {e}")
        return []
def get_link(name):
    """
    Priority:

    1 City packages
    2 Attraction tours
    3 Search fallback
    """

    # Destination first

    dest_id, dest_name = find_code(name)

    if dest_id:

        return f"https://www.travelfika.com/tours/packages/{quote(dest_name)}-tour-packages-{dest_id}"

    product_url = get_travelfika_urls(name)

    if product_url:
        return product_url[0]  # Return the first URL
    # Fallback

    return f"https://www.travelfika.com/experiences/search?query={quote_plus(name)}"


import re

def add_travelfika_links(text):
    """
    Insert Travelfika links safely

    Fixes:

    ✔ No nested <a>
    ✔ No duplicate links
    ✔ Correct URLs
    ✔ One URL only
    """
    doc = nlp(text)
    entity_types = {"GPE","LOC","FAC","ORG","WORK_OF_ART"}
    entities = sorted(
        {ent.text.strip() for ent in doc.ents if ent.label_ in entity_types},
        key=len,
        reverse=True
    )
    linked = set()
    for ent in entities:
        if ent in linked:
            continue
        # Correct usage
        link = get_link(ent)
        if not link:
            continue
        # Already linked?
        pattern = re.compile(
            rf'<a [^>]*>{re.escape(ent)}</a>',
            re.IGNORECASE
        )
        if pattern.search(text):
            continue
        def replace_safe(match):
            before = text[:match.start()]
            inside = before.rfind("<a ") > before.rfind("</a>")
            if inside:
                return match.group(0)
            linked.add(ent)
            return f'<a href="{link}" target="_blank">{ent}</a>'
        text = re.sub(
            r'\b'+re.escape(ent)+r'\b',
            replace_safe,
            text,
            count=1
        )
    return text