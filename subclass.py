import random
import json
import re
import requests
from flask import Flask, request, jsonify
from decouple import config
from keras.models import load_model
from transformers import pipeline
from words import predict_class
import spacy
import dateparser
from word2number import w2n
import openai
from airportsdata import load
from datetime import datetime, timedelta
import spacy
from urllib.parse import quote_plus, quote
import urllib.parse
from url import  normalize_hotels

nlp = spacy.load("en_core_web_sm")


airports = load("IATA")

ner_model = pipeline(
    "ner",
    model="dbmdz/bert-large-cased-finetuned-conll03-english",
    aggregation_strategy="simple"
)

airports = load('IATA')
airport_codes = set(airports.keys())

def is_airport_code(input_str):
    """Match user input (city, IATA code, or airport name) to airport info."""
    user_input = input_str.strip().lower()

    # First try direct code match
    if user_input.upper() in airports:
        code = user_input.upper()
        return code, airports[code]

    # Fallback: search by city or airport name
    for code, data in airports.items():
        city = data.get('city', '').lower()
        name = data.get('name', '').lower()
        if user_input in city or user_input in name:
            return code, data
    return None, None

def extract_journey_type(message):
    
    msg = message.lower()

    if any(k in msg for k in ["round trip", "return", "two way"]):
        return "R"

    if any(k in msg for k in ["one way", "oneway"]):
        return "O"

    return None

def airport_code_info(city_name):
    """Fetch airport code for a given city."""
    base_url = config("AIRPORT_SEARCH_API_URL")
    url = f"{base_url}/airportSearch/{city_name}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        result = data.get('result', [])
        return result[0]
    return None
def extract_travel_dates(text):
    text = text.lower()
    today = datetime.today()

    dates = {"start_date": None, "end_date": None}

    # -------- month names --------
    months = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12
    }

    # -------- end of month --------
    m = re.search(r"end of (\w+)", text)
    if m and m.group(1) in months:
        month = months[m.group(1)]
        year = today.year + (month < today.month)
        start = datetime(year, month, 25)   # heuristic
        dates["start_date"] = start.strftime("%Y-%m-%d")

    # -------- duration --------
    d = re.search(r"(\d+)\s*(day|days|night|nights|week|weeks)", text)
    if d and dates["start_date"]:
        value = int(d.group(1))
        unit = d.group(2)

        if "week" in unit:
            value *= 7

        end = datetime.strptime(dates["start_date"], "%Y-%m-%d") + timedelta(days=value)
        dates["end_date"] = end.strftime("%Y-%m-%d")

    return dates
def build_llm_prompt(text):
    today = datetime.today().strftime("%Y-%m-%d")

    return f"""
Extract travel dates from the text.

Return ONLY JSON:
{{
  "start_date": null,
  "end_date": null
}}

Dates must be ISO YYYY-MM-DD.
Assume future dates only.
Today is {today}.

Text:
\"\"\"{text}\"\"\"
"""
def llm_date_fallback(text):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You extract travel dates."},
            {"role": "user", "content": build_llm_prompt(text)}
        ],
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except Exception:
        return {}
def needs_llm_fallback(dates):
    return not dates.get("start_date")
def normalize_dates(dates):
    if not dates or not dates.get("start_date"):
        return dates

    start = datetime.strptime(dates["start_date"], "%Y-%m-%d")

    if dates.get("end_date"):
        end = datetime.strptime(dates["end_date"], "%Y-%m-%d")
        if end <= start:
            end = start + timedelta(days=1)
    else:
        end = start + timedelta(days=1)

    dates["end_date"] = end.strftime("%Y-%m-%d")
    dates["nights"] = (end - start).days
    return dates
def extract_dates(text):
    # 1️⃣ regex first
    dates =extract_travel_dates(text)

    # 2️⃣ LLM fallback only if needed
    if needs_llm_fallback(dates):
        llm_dates = llm_date_fallback(text)

        # NEVER overwrite regex values
        for k in ("start_date", "end_date"):
            if not dates.get(k) and llm_dates.get(k):
                dates[k] = llm_dates[k]

    return normalize_dates(dates)
def build_flight_payload(date):
    return {
        "departure_date": date["start_date"],
        "return_date": date["end_date"]
    }
def build_hotel_payload(date):
    return {
        "check_in": date["start_date"],
        "check_out": date["end_date"]
    }
    
def fallback_origin_destination(user_message, extracted_locations):
    origin = destination = None

    # Step 1: Check keyword-based mapping using extracted locations
    for location in extracted_locations:
        pattern_origin = re.compile(
            rf'\b(?:in|from|origin(?:\s+is)?|origin\s+city\s+is?)\b[^.]*?\b{re.escape(location)}\b',
            re.IGNORECASE
        )
        pattern_destination = re.compile(
            rf'\b(?:to|destination(?:\s+is)?|destination\s+city\s+is?)\b[^.]*?\b{re.escape(location)}\b',
            re.IGNORECASE
        )

        code, _ = is_airport_code(location)

        if not origin and pattern_origin.search(user_message) and code:
            origin = location
        elif not destination and pattern_destination.search(user_message) and code:
            destination = location

    # Step 2: Regex for "from XXX to YYY"
    fallback_match = re.search(r'\bfrom\s+(\w+)\s+to\s+(\w+)\b', user_message, re.IGNORECASE)
    if fallback_match:
        possible_origin = fallback_match.group(1).strip()
        possible_destination = fallback_match.group(2).strip()

        code, _ = is_airport_code(possible_origin)
        if not origin and code:
            origin = code

        code, _ = is_airport_code(possible_destination)
        if not destination and code:
            destination = code

    # Step 3: Regex for "XXX to YYY" without "from"
    if not origin or not destination:
        simple_match = re.search(r'\b(\w{3})\s+to\s+(\w{3})\b', user_message, re.IGNORECASE)
        if simple_match:
            code1, _ = is_airport_code(simple_match.group(1))
            code2, _ = is_airport_code(simple_match.group(2))

            if not origin and code1:
                origin = code1
            if not destination and code2:
                destination = code2

    return origin, destination

def extract_locations(text):
    ner_results = ner_model(text.title())  
    locations = []
    current_entity = ""
    for entity in ner_results:
        entity_text = entity["word"]
        entity_group = entity["entity_group"]

        if entity_group == "LOC":  
            if entity_text.startswith("##"):
                print('entity_text:', entity_text)
                current_entity += entity_text[2:] 
            else:
                if current_entity:
                    locations.append(current_entity)  
                current_entity = entity_text  

    if current_entity:
        locations.append(current_entity)  

    return locations    
def extract_travel_details(tag,text,currency):   
    intent = tag
    print("intent :",intent)
    if not intent:
        return {"error": "Could not determine whether you need a flight or hotel. Please provide more details."}
    travel_details = {}

    if intent in {"book_flight", "both"}:
        travel_details["flight"] = process_flight(text,currency)
    if intent in {"book_hotel", "both"}:
        travel_details["hotel"] = extract_hotel_details_n(text,currency)

    return travel_details

def process_flight(user_message, currency):

    extracted_locations = extract_locations(user_message)
    print("Extracted Locations:", extracted_locations)
    date = extract_dates(user_message)
    dates=build_flight_payload(date)   
    origin, destination = fallback_origin_destination(user_message, extracted_locations)
    if not origin and len(extracted_locations) >= 1:
        if extracted_locations[0] != destination:
            origin = extracted_locations[0]

        if not destination and len(extracted_locations) >= 2:
            if extracted_locations[1] != origin:
                destination = extracted_locations[1]
    departure_date = dates.get("depart_date")
    return_date = dates.get("return_date")

    roundtrip_keywords = ["round trip", "roundtrip", "return", "two-way", "round-trip"]
    journey_type = "R" if return_date or any(keyword in user_message.lower() for keyword in roundtrip_keywords) else "O"

    if journey_type == "R" and not return_date and departure_date:
        if isinstance(departure_date, str):
            try:
                departure_date = datetime.strptime(departure_date, "%Y-%m-%d")
            except ValueError:
                return_date = "(Please specify a valid return date)"
        return_date = (departure_date + timedelta(days=4)).strftime("%Y-%m-%d") if isinstance(departure_date, datetime) else "(Please specify a return date)"

    if isinstance(departure_date, datetime):
        departure_date = departure_date.strftime("%Y-%m-%d")

    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "journeytype": journey_type,
        "currency": currency,
        
    }
def book_flight(flight_data):
    if not flight_data:
        return {"error": "No valid flight details found."}
    return fetch_flight_booking_details_n(
        origin=flight_data.get("origin", ""),
        destination=flight_data.get("destination", ""),
        departure_date=flight_data.get("departure_date", None),
        return_date=flight_data.get("return_date", None),
        journeytype=flight_data.get("journeytype", ""),
        no_of_adult=flight_data.get("no_of_adult", 1),
        no_of_children=flight_data.get("no_of_children", 0),
        no_of_infant=flight_data.get("no_of_infant", 0),
        ClassType=flight_data.get("ClassType", "Economy"),
        currency=flight_data.get("currency", "USD")
    )    
def fetch_flight_booking_details_n(origin, destination, departure_date, return_date, journeytype, no_of_adult, no_of_children, no_of_infant, ClassType, currency):
    """Fetch flight details (handles both one-way & round-trip)."""

    origin_code = airport_code_info(origin).get('Airport_Code', None)
    destination_code = airport_code_info(destination).get('Airport_Code', None)
    origin_airport = airport_code_info(origin).get('Airport_Name', None)
    origin_city = airport_code_info(origin).get('City_name', None)
    origin_country = airport_code_info(origin).get('Country_Name', None)
    dest_code = airport_code_info(destination).get('Airport_Code', None)
    dest_airport = airport_code_info(destination).get('Airport_Name', None)
    dest_city = airport_code_info(destination).get('City_name', None)
    dest_country = airport_code_info(destination).get('Country_Name', None)
    if not origin_code or not destination_code:
        return None
    print("Airport Code of Origin:", origin_code)
    print("Airport Code of Destination:", destination_code)
    print("journeyType:", journeytype)
    print("Departure Date:", departure_date)
    print("Return Date:", return_date if return_date else "N/A")
    print("Class Type:", ClassType)
    trip_type=journeytype
 
    url = config("FLIGHT_SEARCH_API_URL_ONEWAY")
    data = {
         "JourneyType": journeytype,
          "OriginDestination":[
            {"Origin": origin_code, 
             "Destination": destination_code, 
             "DepartureDate": departure_date}
            ],
          "ClassType":ClassType,
        "NoOfInfant": {
        "Count": 0,
        "Age": {}
    },
    "NoOfChildren": {
        "Count": 0,
        "Age": {}
    },
    "NoOfAdult": {
        "Count": 1
    },
    "PreferredArilines": [],
    "PreferredCurrency": currency,
    "OtherInfo": {
        "RequestedIP": "",
        "TransactionId": ""
    },
    "MultiCityTripdata": [],
    "Incremental": "false",
    "NearLocations": "true",
    "DTK": "true",
    "BrandedFares": "true",
    "sectorId": 1
}
    if journeytype=="O":
        response = requests.post(url, json=data)
        s=[]
        if response.status_code == 200:
            result = response.json()
            result_list = []
            for flight in result.get('result', [])[:4]:
                journey_info = flight.get('Itinerary', [])[0].get('JourneyInfo', {})
                origin_destination = flight.get('Itinerary', [])[0].get('OriginDestination', [])
                fare_breakdown = flight.get('FareBreakdown', [])[0].get('GrossFare','')
                destination_airport = origin_destination[-1].get('DestinationAirportName', 'Unknown Destination')
                id = flight.get('IteneraryRefID', "")
                
                
                result = {'JourneyInfo': journey_info,
                      'OriginDestination': origin_destination,
                      'FareBreakdown': fare_breakdown,
                      'ID':id}
                result_list.append(result)
            return result_list
        else:
            print("Failed to retrieve data. Status code:", response.status_code)
            print("Error Response:", response.text)
            return response

    elif journeytype == "R" and return_date:
        result_list=[]
        url = config("FLIGHT_SEARCH_API_URL_ROUNDTRIP")
        data["OriginDestination"].append(
            {"Origin": destination_code, "Destination": origin_code, "DepartureDate": return_date}
        )
        response = requests.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            outbound_flights =result['result']['result']['outboundResult']
            for flight in outbound_flights[:3]:
                journey_info = flight.get('JourneyInfo', {})
                origin_destination = flight.get('FlightsList', [])
                brand_attributes=flight.get('BrandAttributes',[])
                cabin_class = next((x["cabinClass"] for x in brand_attributes if x.get("cabinClass")), None)
                fare_breakdown = flight.get('minGrossFare','')
                destination_airport = origin_destination[-1].get('DestinationAirportName', 'Unknown Destination')
                id = flight.get('ItineraryId', "")
                flight.get('IteneraryRefID', "")
                
                result = {'JourneyInfo': journey_info,
                      'OriginDestination': origin_destination,
                      'FareBreakdown': fare_breakdown,
                      'ID':id,
                      'start_date':departure_date,
                      'end_date':return_date,
                      'CabinClass':cabin_class}
                result_list.append(result)
            return result_list
        else:
            print("Failed to retrieve data. Status code:", response.status_code)
            print("Error Response:", response.text)
            return response
    else:
        print("Failed to retrieve data. Status code:", response.status_code)
        print("Error Response:", response.text)
        return response      
def extract_airport_from_text(text):
    pattern = r'([A-Za-z\s]+Airport)\s*\(([A-Z]{3})\)'
    match = re.search(pattern, text)

    if match:
        return {
            "airport_name": match.group(1).strip(),
            "airport_code": match.group(2).strip()
        }
    return None

def extract_destination(text):
    # 1️⃣ Try airport extractor
    dest = extract_airport_from_text(text)
    if dest:
        return dest

    # 2️⃣ Fallback: spaCy GPE/LOC
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ["GPE", "LOC"]:
            return ent.text

    return None

from datetime import datetime, timedelta


def suggest_flights(current_city, destination, currency="INR"):
    print("✈️ suggest_flights called:", current_city, "→", destination)

    # 1️⃣ Get airport details
    origin_info = airport_code_info(current_city)
    destination_info = airport_code_info(destination)

    if not origin_info:
        return {"error": f"No airport found for origin city: {current_city}"}

    if not destination_info:
        return {"error": f"No airport found for destination: {destination}"}

    origin_code = origin_info.get("Airport_Code")
    destination_code = destination_info.get("Airport_Code")

    if not origin_code or not destination_code:
        return {"error": "Airport code missing for origin or destination"}

    # 2️⃣ Travel dates
    departure_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    return_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

    # 3️⃣ Call flight search API
    try:
        flights = fetch_flight_booking_details_n(
            origin=origin_code,
            destination=destination_code,
            departure_date=departure_date,
            return_date=return_date,
            journeytype="R",         
            no_of_adult=1,
            no_of_children=0,
            no_of_infant=0,
            ClassType="E",          
            
            currency=currency
        )

        if not flights:
            return {
                "origin": origin_code,
                "destination": destination_code,
                "departure_date": departure_date,
                "return_date": return_date,
                "flights": [],
                "message": "No flights found for selected route"
            }

    except Exception as e:
        print("✈️ Flight API error:", e)
        return {
            "error": "Flight service error",
            "details": str(e)
        }

    # 4️⃣ Final structured response
    return {
        "origin": {
            "city": current_city,
            "airport_code": origin_code
        },
        "destination": {
            "city": destination,
            "airport_code": destination_code
        },
        "departure_date": departure_date,
        "return_date": return_date,
        "flights": flights
    }
from datetime import datetime, timedelta

def suggest_hotels(destination, currency):
    """
    Suggest hotels using destination city only.
    Uses default dates and occupancy.
    """

    if not destination:
        return "Please tell me the destination city 🏨", None

    # 🔹 Default stay: 3 nights from tomorrow
    checkin_date = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    checkout_date = (datetime.today() + timedelta(days=4)).strftime("%Y-%m-%d")

    # 🔹 Call hotel API
    api_response = find_hotel_in_city_n(
        origin=destination,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        currency=currency,
        no_of_room=1,
        no_of_adult=2,
        no_of_children=0
    )

    # 🔹 Normalize & generate hotel DETAIL URLs
    hotels = normalize_hotels(api_response)

    if not hotels:
        return f"No hotels found in {destination} 😔", None

    return hotels, None

def get_city_code(city):
    base_url = config("city_cod")
    url = f"{base_url}?search={city}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json().get('destinationSuggestions', [])
        if data:
            city_info = data[0].split(', ')
            city_code = city_info
            print(city_code)
            return city_code 
        else:
            return "hotels not available"

def find_hotel_in_city_n(origin,checkin_date,checkout_date,currency,no_of_room, no_of_adult,no_of_children):
    today = checkin_date
    return_date = checkout_date
    city_code = get_city_code(origin)
    url=config("hotel_find")
    payload = {
        "stay": {
            "checkIn": checkin_date,
            "checkOut": checkout_date,
        },
        "occupancies": [
            {
                "rooms": int(no_of_room),
                "adults":  int(no_of_adult),
                "children": 0,
                "paxes": []
            }
                ],
        "destination": {
            "code": city_code[0]
        },
        "filters": {},
        "sortType": "R",
        "hotelName": "",
        "currency":currency
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json()
        hotel_table = [] 
        params = f'[{{"rooms":{no_of_room},"adults":2,"children":0,"paxes":[]}}]'
        encoded_params = urllib.parse.quote(params)
        
        if "Results" in data:
            hotel_table = []
            hotelname=[]
            hotel_links=[]
            for hotel in data["Results"][:5]:
                hotelname.append(hotel.get("name", "N/A"))
                name = hotel.get("name", "N/A")
                image = hotel.get("images", [""])[0]   # get first image
                geo = hotel.get("GeoCode", {})
               # Create clickable hotel name
                hotel_table.append({
                    'Name': hotel.get("name", "N/A"),
                    'ADDRESS': hotel.get("address", "N/A"),
                    'code':hotel.get("code"),
                    'Price': "${}".format(hotel.get("minRate", "N/A")),
                    'Rating': hotel.get("rating", "N/A"),
                    'Imageurl': hotel.get("images", "N/A")[0],
                    'checkin_date': checkin_date,
                    'checkout_date': checkout_date,
                    "no_of_room": no_of_room,
                    "city_code": city_code[0],
                    "city_name": city_code[1],
                    "state": city_code[2],
                    "latitude": geo.get("latitude"),
                    "longitude": geo.get("longitude"),
                })
                data={'hotel_name':hotel_links}

        return hotel_table
    else:
        print("Error:", response.status_code)
def extract_hotel_details_n(text, currency):
    """Extract hotel-related details from user input."""
    locations = extract_locations(text)
    date = extract_dates(text)
    dates = build_hotel_payload(date)
    print("dates extracted for hotel:", dates)
    check_in_date = dates["check_in"]
    check_out_date = dates["check_out"]
    city = locations[0] if locations else None
    response = {
        "city": city,
        "check_in": check_in_date,
        "check_out": check_out_date,
        "adults": 1,
        "children": 0,
        "currency": currency
    }
    if not city:
        response["message"] = "Sure! Could you tell me which city you're planning to stay in?"

    return response        
def book_hotel(hotel_data):
    """Fetch hotel booking details and normalize the response."""

    if not hotel_data:
        return {"error": "No valid hotel details found."}

    # 🔹 Call hotel search API
    api_response = find_hotel_in_city_n(
        origin=hotel_data.get("city", ""),
        checkin_date=hotel_data.get("check_in"),
        checkout_date=hotel_data.get("check_out"),
        currency=hotel_data.get("currency", "USD"),
        no_of_room=hotel_data.get("no_of_room", 1),
        no_of_adult=hotel_data.get("adults", 1),
        no_of_children=hotel_data.get("children", 0)
    )

    # 🔹 Normalize response (handles dict / list safely)
    try:
        normalized_hotels = normalize_hotels(api_response)
    except Exception as e:
        return {"error": str(e)}
    return normalized_hotels
