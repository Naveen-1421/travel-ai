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
from subclass import extract_dates, fetch_flight_booking_details_n, extract_travel_details,extract_journey_type,book_flight,extract_locations,airport_code_info,extract_destination,suggest_flights
from subclass import extract_hotel_details_n,book_hotel,build_hotel_payload,find_hotel_in_city_n,extract_travel_dates,build_flight_payload,fallback_origin_destination
from url import normalize_hotels
def build_next_suggestions(flow_type, context):
    """
    flow_type: 'flight' | 'hotel' | 'general'
    context: dict with origin/destination/city
    """

    suggestions = []

    if flow_type == "flight":
        destination = context.get("destination")

        if destination:
            suggestions = [
                f"🏨 Book hotel in {destination}",
                f"🎟️ Things to do in {destination}",
                f"📦 Show tour packages for {destination}"
            ]

    elif flow_type == "hotel":
        city = context.get("city")

        if city:
            suggestions = [
                f"✈️ Find flights to {city}",
                f"🎟️ Explore attractions in {city}",
                f"🚗 Airport transfers in {city}"
            ]

    elif flow_type == "general":
        suggestions = [
            "✈️ Book flights",
            "🏨 Book hotels",
            "📦 Tour packages",
            "🎟️ Things to do"
        ]

    return suggestions


conversation = {}

def handle_flight_flow(chat_id, user_message, currency):
    state = conversation.setdefault(chat_id, {})
    #print("✈️ CURRENT STATE:", state)

    # ---------- EXTRACT EVERYTHING ----------
    extracted_locations = extract_locations(user_message)
    journey = extract_journey_type(user_message)   # O / R
    dates = extract_dates(user_message)
    origin_fall,destination_fall=fallback_origin_destination(user_message, extracted_locations)

    #print("✈️ Extracted locations:", extracted_locations)
    #print("✈️ Extracted journey:", journey)
    #print("✈️ Extracted dates:", dates)

    # ---------- FILL STATE (OPPORTUNISTIC) ----------

    if not state.get("origin") and extracted_locations:
        if extracted_locations[0] != destination_fall:
            state["origin"] = extracted_locations[0]

    if not state.get("destination") and extracted_locations:
        if state.get("origin") and len(extracted_locations) > 1:
            state["destination"] = extracted_locations[1]
        elif extracted_locations[0] != state.get("origin"):
            state["destination"] = extracted_locations[0]

    if not state.get("journey_type") and journey:
        state["journey_type"] = journey

    if not state.get("departure_date") and "start_date" in dates:
        state["departure_date"] = dates["start_date"]

    if (
        state.get("journey_type") == "R"
        and not state.get("return_date")
        and "end_date" in dates
    ):
        state["return_date"] = dates["end_date"]

    # ---------- ASK ONLY WHAT IS MISSING ----------

    if not state.get("origin"):
        return {"responses": "From which city are you flying?"}, None

    if not state.get("destination"):
        return {
            "responses": f"Flying from {state['origin']}. Where are you flying to?"
        }, None

    if not state.get("journey_type"):
        return {"responses": "Is this a one-way or round-trip journey?"}, None

    if not state.get("departure_date"):
        return {"responses": "When is your departure date?"}, None

    if state["journey_type"] == "R" and not state.get("return_date"):
        return {"responses": "When is your return date?"}, None

    # ---------- ALL DATA COLLECTED ----------
    #print("✅ FINAL STATE:", state)

    # ---------- AIRPORT LOOKUP ----------
    origin_info = airport_code_info(state["origin"])
    dest_info = airport_code_info(state["destination"])

    if not origin_info or not dest_info:
        return {
            "responses": "Airport service is temporarily unavailable. Please try again later."
        }, None

    flight_data = fetch_flight_booking_details_n(
        origin=origin_info["Airport_Code"],
        destination=dest_info["Airport_Code"],
        departure_date=state["departure_date"],
        return_date=state.get("return_date"),
        journeytype=state["journey_type"],
        no_of_adult=1,
        no_of_children=0,
        no_of_infant=0,
        ClassType="E",
        currency=currency
    )

    # ---------- CLEAR STATE ----------
    #print("✈️ Fetched flight data:", flight_data)
    
    response = {
        "responses": "Here are the best flight options ✈️",
        "data": flight_data,
         "next_suggestions": build_next_suggestions(
        "flight",
        {"destination": state["destination"]}
    )
    }
    
    conversation.pop(chat_id, None)
    return response,None

def handle_hotel_flow(chat_id, user_message, currency):
    state = conversation.setdefault(chat_id, {})
    #print("🏨 CURRENT HOTEL STATE:", state)

    # ---------- EXTRACT EVERYTHING ----------
    extracted_locations = extract_locations(user_message)
    raw_dates = extract_dates(user_message)
    dates = build_hotel_payload(raw_dates)

    #print("🏨 Extracted locations:", extracted_locations)
    #print("🏨 Extracted hotel dates:", dates)

    # ---------- FILL STATE (OPPORTUNISTIC) ----------

    # City
    if not state.get("city") and extracted_locations:
        state["city"] = extracted_locations[0]

    # Dates
    if not state.get("checkin_date") and dates.get("check_in"):
        state["checkin_date"] = dates["check_in"]

    if not state.get("checkout_date") and dates.get("check_out"):
        state["checkout_date"] = dates["check_out"]

    # ---------- ASK ONLY WHAT IS MISSING ----------

    if not state.get("city"):
        return {"responses": "Which city are you looking to stay in?"}, None

    if not state.get("checkin_date"):
        return {"responses": "When is your check-in date?"}, None

    if not state.get("checkout_date"):
        return {"responses": "When is your check-out date?"}, None

    # ---------- DEFAULTS ----------
    state.setdefault("adults", 2)
    state.setdefault("rooms", 1)

    #print("✅ FINAL HOTEL STATE:", state)

    # ---------- FETCH HOTELS ----------
    hotel_data = find_hotel_in_city_n(
        origin=state["city"],
        checkin_date=state["checkin_date"],
        checkout_date=state["checkout_date"],
        no_of_adult=state["adults"],
        no_of_children=0,
        no_of_room=state["rooms"],
        currency=currency
    )

    hotel = normalize_hotels(hotel_data)

    # ---------- CLEAR STATE ----------
   

    response= {
        "responses": f"Here are the best hotels in {state['city']} 🏨",
        "data": hotel,
        "next_suggestions": build_next_suggestions(
            "hotel",
            {"city": state["city"]}
        )
    }
    conversation.pop(chat_id, None)
    return response,None


def generate_gpt_recommendations(user_id, context):
    """
    context example:
    {
        "flow": "flight",
        "origin": "Chennai",
        "destination": "Dubai",
        "departure_date": "2026-06-10"
    }
    """

    prompt = f"""
You are a smart travel recommendation engine.

Based on this context:
{json.dumps(context, indent=2)}

Generate 3 smart next-step travel suggestions.

Rules:
- Keep suggestions short (max 10 words)
- Make them actionable
- No explanation
- Return ONLY JSON array

Example output:
[
  "Book hotels in Dubai",
  "Explore top attractions in Dubai",
  "Check tour packages for Dubai"
]
"""

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You generate travel next-step suggestions."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=200
    )

    try:
        return json.loads(response.choices[0].message["content"])
    except:
        return []
