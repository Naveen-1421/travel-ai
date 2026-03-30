import openai
from flask import Flask, request, jsonify
from decouple import config

# Set OpenAI API key
openai.api_key = config("openai")


# Dictionary to store user sessions
user_sessions = {}

def generate_response(user_id, user_input, query_type,category):
    """
    Generate a response dynamically using GPT based on query type, user ID, and category for thematic queries.

    Args:
        user_id (str): Unique identifier for the user.
        user_input (str): The user's query.
        query_type (str): The type of query ("flight", "hotel", "attraction", or "thematic").
        category (str): Thematic category for thematic queries (e.g., "adventure", "romance").
    Returns:
        str: The generated response in Rich Text format (HTML).
    """
    # Initialize session if not already exists
    if user_id not in user_sessions:
        user_sessions[user_id] = []

    # Append user's query to session history
    user_sessions[user_id].append({"role": "user", "content": user_input})

    if query_type == "flight":
        return flight_advisor(user_id, user_input)
    elif query_type == "hotel":
        return hotel_advisor(user_id, user_input)
    elif query_type == "attractions":
        return attraction_advisor(user_id, user_input)
    else: 
        return thematic_advisor(user_id,user_input,query_type)
    
def flight_advisor(user_id, prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": """
            You are a helpful travel advisor from Travelfika who provides flight suggestions based on user queries.
            For bookings, you can use our website Travelfika. (since the bot is part of the Travelfika website)
            **Flights:** Provide options with:
            - Flight number
            - Airline
            - Boardpoint (departure location)
            - Destination (arrival location)
            - Stops (direct or with stops)
            - Departure time
            - Arrival time
            - Price
        """}] + user_sessions[user_id] + [{"role": "user", "content": prompt}]
    )
    raw_response = response['choices'][0]['message']['content']
    raw_response = raw_response.replace('\n', '<br>')
    raw_response = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_response)
    user_sessions[user_id].append({"role": "assistant", "content": raw_response})
    return{ "responses" :f"<div><strong>Flight Details:</strong><br>{raw_response}</div>"}

def hotel_advisor(user_id, prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": """
            You are a helpful travel advisor who provides hotel suggestions based on user queries.
            For bookings, you can use our website Travelfika. (since the bot is part of the Travelfika website)
            **Hotels:** Provide options with:
            - Hotel name
            - Location (city or area)
            - Rating (out of 5 stars)
            - Price per night 
            - Amenities (e.g., free Wi-Fi, breakfast included, pool, etc.)
        """}] + user_sessions[user_id] + [{"role": "user", "content": prompt}]
    )
    raw_response = response['choices'][0]['message']['content']
    raw_response = raw_response.replace('\n', '<br>')
    raw_response = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_response)
    user_sessions[user_id].append({"role": "assistant", "content": raw_response})
    return{"responses" :f"<div><strong>Hotel Details:</strong><br>{raw_response}</div>"}
import re
def attraction_advisor(user_id, prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": """
            You are a helpful travel advisor who provides attraction suggestions based on user queries.
            For bookings, you can use our website Travelfika. (since the bot is part of the Travelfika website)
            **Attractions:** Provide options with:
            - Attraction name
            - Location (city or area)
            - Description
            - Rating (out of 5 stars)
            - Entry fee (if applicable)
            - Opening hours
        """}] + user_sessions[user_id] + [{"role": "user", "content": prompt}]
    )
    raw_response = response['choices'][0]['message']['content']
    raw_response = raw_response.replace('\n', '<br>')
    raw_response = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_response)
    user_sessions[user_id].append({"role": "assistant", "content": raw_response})
    return {"responses" :f"<div><strong>Attraction Details:</strong><br>{raw_response}</div>"}

def thematic_advisor(user_id,prompt,query_type):    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": f"""
            You are a thematic travel advisor specializing in {query_type}. Your task is to provide detailed travel suggestions based on the category provided by the user.
            When responding, include relevant details such as:
            - Name of the destination/place
            - Activities and experiences suited for the category
            - Special features
            - Price range or budget (if applicable)
            - Any other relevant details for {query_type}.
        """}] + user_sessions[user_id] + [{"role": "user", "content": prompt}]
    )
  
    raw_response = response['choices'][0]['message']['content']
    raw_response = raw_response.replace('\n', '<br>')
    raw_response = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_response)
    user_sessions[user_id].append({"role": "assistant", "content": raw_response})
    return{"responses" :f"<div><strong>{query_type.capitalize()} Details:</strong><br>{raw_response}</div>"}
