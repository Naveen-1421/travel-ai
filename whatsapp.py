### whats app functions 
from datetime import datetime
import re
from datetime import date, timedelta
from decouple import config
from flask import Flask, request, jsonify
from dateutil.parser import parse, ParserError
import random
import spacy
import json
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from datetime import datetime
import random
from datetime import datetime, timedelta
import requests
import geocoder
import phonenumbers
from phonenumbers import geocoder, region_code_for_number
import urllib.parse

def identify_response_type(response):
    # Representative keywords for different response types
    flight_keyword = "JourneyInfo"
    attraction_keyword = "product_code"
    hotel_keyword = "ADDRESS"
    
    # Check if the response contains the flight keyword
    if flight_keyword in response[0]:
        return convert_flight_to_text(response)
    
    # Check if the response contains the attraction keyword
    elif attraction_keyword in response[0]:
        return convert_attraction_to_text(response)
    
    # Check if the response contains the hotel keyword
    elif hotel_keyword in response[0]:
        return convert_hotel_to_text(response)
    
    # If no keyword is found, return Unknown
    return "Unknown Response"

def convert_flight_to_text(flights):
    result = ""
    flight_count = 1  # Initialize flight count
    for flight in flights:
        result += f"*Flight {flight_count} Details:*\n"
        fare_breakdown = flight.get('FareBreakdown', 0.0)  # Handle missing FareBreakdown gracefully
        result += f"Fare Breakdown: ₹{fare_breakdown:.2f}\n"
        
        # Process outbound flight details
        result += "*Outbound Flight:*\n"
        for leg in flight['OriginDestination']:
            arrival_details = datetime.strptime(leg['ArrivalTime'], "%Y-%m-%dT%H:%M:%S")
            arrival_time = datetime.strptime(leg['ArrivalTime'], "%Y-%m-%dT%H:%M:%S") # Get the date
            arrival_time = arrival_time.strftime("%a %d %b %Y, %I:%M %p") 
            departure_details = datetime.strptime(leg['DepartureTime'], "%Y-%m-%dT%H:%M:%S") # Get the date
            departure_time =datetime.strptime(leg['DepartureTime'], "%Y-%m-%dT%H:%M:%S")
            departure_time =departure_time.strftime("%a %d %b %Y, %I:%M %p") 
            #departure_time = leg['DepartureTime']
            #arrival_time = leg['ArrivalTime']
            duration = leg['Duration']
            carrier = leg['Carrier']
            destination_airprt = leg['DestinationAirportName']
            origin_airport_name = leg['OriginAirportName']
            cabin_class = leg['CabinClass']
            MarketingAirlineName = leg['MarketingAirlineName']
            
            result += f"    AirlineName {MarketingAirlineName} ({carrier})\n"
            result += f"    Departure: {departure_time}\n"
            result += f"    Arrival: {arrival_time}\n"
            result += f"    Duration: {duration}\n"
            result += f"    Origin Airport Name: {origin_airport_name}\n"
            result += f"    Destination Airport Name: {destination_airprt}\n"
            result += f"    Cabin Class: {cabin_class}\n"
            #result += f"    Airline Baggage Allowance: {leg['AirBaggageAllowance']}\n\n"

        # Check if a return flight exists and process it
        if 'return' in flight and flight['return']:
            result += "*Return Flight:*\n"
            for leg in flight['return']:
                arrival_details = datetime.strptime(leg['ArrivalTime'], "%Y-%m-%dT%H:%M:%S")
                arrival_time = datetime.strptime(leg['ArrivalTime'], "%Y-%m-%dT%H:%M:%S")
                arrival_time = arrival_time.strftime("%a %d %b %Y, %I:%M %p")  # Get the date
                departure_details = datetime.strptime(leg['DepartureTime'], "%Y-%m-%dT%H:%M:%S") # Get the date
                departure_time =datetime.strptime(leg['DepartureTime'], "%Y-%m-%dT%H:%M:%S")
                departure_time =departure_time.strftime("%a %d %b %Y, %I:%M %p") 
                #departure_time = leg['DepartureTime']
                #arrival_time = leg['ArrivalTime']
                duration = leg['Duration']
                carrier = leg['Carrier']
                destination_airprt = leg['DestinationAirportName']
                origin_airport_name = leg['OriginAirportName']
                cabin_class = leg['CabinClass']
                MarketingAirlineName = leg['MarketingAirlineName']
                
                result += f"    AirlineName {MarketingAirlineName} ({carrier})\n"
                result += f"    Departure: {departure_time}\n"
                result += f"    Arrival: {arrival_time}\n"
                result += f"    Duration: {duration}\n"
                result += f"    Origin Airport Name: {origin_airport_name}\n"
                result += f"    Destination Airport Name: {destination_airprt}\n"
                result += f"    Cabin Class: {cabin_class}\n"
                #result += f"    Airline Baggage Allowance: {leg['AirBaggageAllowance']}\n\n"

        flight_count += 1  # Increment flight count for the next flight

    return result

def convert_attraction_to_text(attractions):
    result = ""
    attraction_count = 1  # Initialize attraction count
    for attraction in attractions:
        result += f"**Attraction {attraction_count} Details:**\n"
        result += f"Name: {attraction['Name']}\n"
        result += f"Price: {attraction['Price$']}\n"
        result += f"City: {attraction['city']}\n"
        result += f"Product Code: {attraction['product_code']}\n"
        result += f"Rating: {attraction['rating']} stars\n"
        
        attraction_count += 1  # Increment attraction count for the next attraction

    return result

def convert_hotel_to_text(hotels):
    result = ""
    hotel_count = 1  # Initialize hotel count
    for hotel in hotels:
        result += f"**Hotel {hotel_count} Details:**\n"
        result += f"Name: {hotel['Name']}\n"
        result += f"Address: {hotel['ADDRESS']}\n"
        result += f"City: {hotel['city_name']}, {hotel['state']}\n"
        result += f"Price: {hotel['Price']}\n"
        result += f"Rating: {hotel['Rating']}\n"
        result += f"Check-in Date: {hotel['checkin_date']}\n"
        result += f"Check-out Date: {hotel['checkout_date']}\n"
        result += f"Rooms: {hotel['no_of_room']}\n"
      

        hotel_count += 1  # Increment hotel count for the next hotel

    return result

COUNTRY_TO_CURRENCY = {
    "US": "USD",  # United States
    "IN": "INR" # India
    }
    
def detect_currency(phone_number):
    """Detect the currency based on the phone number's country code."""
    try:
        # Parse the phone number
        parsed_number = phonenumbers.parse(phone_number)
        
        # Get the region code (e.g., "US" for United States)
        region_code = region_code_for_number(parsed_number)
        
        # Find the currency using the region code
        currency = COUNTRY_TO_CURRENCY.get(region_code, "USD")
        print(region_code)
        return currency
    except Exception as e:
        print(f"Error detecting currency: {e}")
        return "USD"
    
  
ACCESS_TOKEN = config("ACCESS_TOKENS")
PHONE_NUMBER_ID =config("NUMBER_ID")
VERIFY_TOKEN =config("VERIFY_TOKENS")
import urllib.parse
def hoteltemplate(hotels,to):
    whatsapp_api_url = f'https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages'
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    constant_value = "N/A"

    # Extract data for the first hotel
    first_hotel_data = hotels[0]
    city_code = first_hotel_data.get("city_code", constant_value)
    city_name = first_hotel_data.get("city_name", constant_value).replace(" ", "-")
    state = first_hotel_data.get("state", constant_value).replace(" ", "-")
    checkin_date = first_hotel_data.get("checkin_date", constant_value)
    checkout_date = first_hotel_data.get("checkout_date", constant_value)
    rooms = first_hotel_data.get("no_of_room", constant_value)

    # Manually format the parameters for the URL
    params = f'[{{"rooms":{rooms},"adults":2,"children":0,"paxes":[]}}]'
    currency = detect_currency(to)
    # Construct the URL without encoding
   # base_url = "https://www.travelfika.com/"
    final_url = (
    f"hotel/listing-stay/"
    f"{city_code},{city_name},{state}/"
    f"{params}/1/0/0/{checkin_date}/{checkout_date}/0"
)


    # Log the URL for debugging
    print(f"Generated URL: {final_url}")
    for hotel in hotels:
        payload = {
    "messaging_product": "whatsapp",
    "to": to,  # Replace with the recipient's phone number
    "type": "template",
    "template": {
        "name": "tf_template",
        "language": {"code": "en_US"},
        "components": [
            {
                "type": "body",
                "parameters": [
        
                      {
                    "type": "text", "text": "hotel"},
                    {"type": "text", "text": f'*{hotel["Name"]}*'},
                    {"type": "text", "text": f'*{currency} {hotel["Price"].replace("$", "")}*'},
                    {"type": "text", "text": f'*{hotel["Rating"]}*'},
                ]
            },
            {
                "type": "header",
                "parameters": [
                    {"type": "image", "image": {"link": hotel["Imageurl"]}}  # Use hotel image URL
                ]
            },
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": 
                [
                    {"type": "text", "text": final_url}  # Include the final URL as a button
                ]
            }
        ]
    }
}


        
        # Send the request
        response = requests.post(whatsapp_api_url, headers=headers, json=payload)
    
        print(response.json())

def attractiontemplate(attraction,to):
    whatsapp_api_url = f'https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages'
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    constant_value = "N/A"
    currency = detect_currency(to)
    # Extract data for the first hotel
    first_attraction_data = attraction[0]
    city_code = first_attraction_data.get("code", constant_value)
    city_name = first_attraction_data.get("city", constant_value).replace(" ", "-")
    #state = first_attraction_data.get("state", constant_value).replace(" ", "-")
    start_date = first_attraction_data.get("checkin_date", constant_value)
    end_date = first_attraction_data.get("checkout_date", constant_value)
    #rooms = first_attraction_data.get("no_of_room", constant_value)
    attraction_id = 0
    # Manually format the parameters for the URL
    #params = f'[{{"rooms":{rooms},"adults":2,"children":0,"paxes":[]}}]'
     
    # Construct the URL without encoding
   # base_url = "https://www.travelfika.com/"
    city_name_formatted = city_name.replace(" ", "-")  # Replace spaces with hyphens
    final_url = (
        f"tours/{city_name_formatted}/{city_code}"
        f"?startDate={start_date}&endDate={end_date}&attractionId={attraction_id}"
    )
    


    # Log the URL for debugging
    print(f"Generated URL: {final_url}")
    for hotel in attraction:
        payload = {
    "messaging_product": "whatsapp",
    "to": to,  # Replace with the recipient's phone number
    "type": "template",
    "template": {
        "name": "hotel2",
        "language": {"code": "en_US"},
        "components": [
            {
                "type": "body",
                "parameters": [
        
                      {
                    "type": "text", "text": "attraction"},
                    {"type": "text", "text": f'*{hotel["Name"]}*'},
                    {"type": "text", "text": f'*{currency} {hotel["Price$"]}*'},
                    {"type": "text", "text": f'*{hotel["rating"]} Star*'},
                ]
            },
            {
                "type": "header",
                "parameters": [
                    {"type": "image", "image": {"link": hotel["URL"]}}  # Use hotel image URL
                ]
            },
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": 
                [
                    {"type": "text", "text": final_url}  # Include the final URL as a button
                ]
            }
        ]
    }
}


        
        # Send the request
        response = requests.post(whatsapp_api_url, headers=headers, json=payload)
    
        print(response.json())
    
def extract_date(timestamp):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").strftime("%b %d")  # Jan 29

def extract_time(timestamp):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").strftime("%I:%M %p").lstrip("0")

def extract_round_trip_details(flight_data,to):
    outbound_flight1 = flight_data[0]['OriginDestination'][0]
    outbound_flight2 = flight_data[1]['OriginDestination'][0]
    destination_out=flight_data[0]['OriginDestination'][-1]
    destination_out1=flight_data[1]['OriginDestination'][-1]
    return_flight1 = flight_data[0]['return'][0]
    return_flight2 = flight_data[1]['return'][0]
    destination_return=flight_data[0]['return'][-1]
    destination_return1=flight_data[1]['return'][-1]
    print(destination_return1)
    o1=[segment.get('Duration') for segment in flight_data[0]['OriginDestination']]
    currency = detect_currency(to)
    r1=[segment.get('Duration') for segment in flight_data[0]['return']]
    r2=[segment.get('Duration') for segment in flight_data[1]['return']]
    o2=[segment.get('Duration') for segment in flight_data[1]['OriginDestination']]


    #print("Return Flight 1 Duration:",flight_data[0]['return'].get('Duration'))
    #print("Outbound Flight 2 Duration:", flight_data[1]['OriginDestination'].get('Duration'))
    #print("Return Flight 2 Duration:", flight_data[1]['return'].get('Duration'))

    final_url=generate_flight_url(flight_data)
    ACCESS_TOKENS= 'EAAIoiNqc3okBO1uIsCdFmFWF9fPH7rgd4ebgfzgRJ1zGONPY7DoVn98exDUdGzfeOsu9dcos8tVCucnxKiIzAPjzUblQ4braEQ9WFn5GwNmOFom4ZB5AxK64RtXCf0r4uNzkWig2HwWsDlHQW5ju0TZCdPnjAyerZBcPRGtmfDpqvNpg2BgGA8RU8KjxlEvywZDZD'
    PHONE_NUMBER_ID = '568728092971072' 
    whatsapp_api_url = f'https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages'
   
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKENS}",
        "Content-Type": "application/json"
    }

    payload = {
    "messaging_product": "whatsapp",
    "to": to,  # Replace with the recipient's phone number
    "type": "template",
    "template": {
        "name": "flight_roundtrip",
        "language": {"code": "en_US"},
        "components": [
            {
                "type": "body",
                "parameters": [
        
                      {
                    "type": "text", "text" :outbound_flight1['CabinClass']},
                    {"type": "text", "text":f"{outbound_flight1['OriginCode']} to {destination_out['DestinationCode']}"},
                    {"type": "text", "text":extract_date(outbound_flight1['DepartureTime'])},
                    {"type": "text", "text":f"{return_flight1['OriginCode']} to {destination_return['DestinationCode']}"},
                    {"type": "text", "text":extract_date(return_flight1['DepartureTime'])},
                    {"type": "text", "text":outbound_flight1['MarketingAirlineName']},
                    {"type": "text", "text":f"  • {extract_date(outbound_flight1['DepartureTime'])}@{extract_time(outbound_flight1['DepartureTime'])}"},
                    {"type": "text", "text":f"  • {add_durations(o1)}+Layover({destination_out['LayoverTimeInMinutes']})"},
                    {"type": "text", "text":return_flight1['MarketingAirlineName']},
                    {"type": "text", "text":f"  • {extract_date(return_flight1['DepartureTime'])}@{extract_time(return_flight1['DepartureTime'])}"},
                    {"type": "text", "text":f"  • {add_durations(r1)}+Layover({destination_return['LayoverTimeInMinutes']})"},
                    {"type": "text", "text":f"{currency} {flight_data[0]['FareBreakdown']}"},
                    {"type": "text", "text":outbound_flight2['MarketingAirlineName']},
                    {"type": "text", "text":f"  • {extract_date(outbound_flight2['DepartureTime'])}@{extract_time(outbound_flight2['DepartureTime'])}"},
                    {"type": "text", "text":f"  • {add_durations(o2)}+Layover({destination_out1['LayoverTimeInMinutes']})"},
                    {"type": "text", "text":return_flight2['MarketingAirlineName']},
                    {"type": "text", "text":f"  • {extract_date(return_flight2['DepartureTime'])}@{extract_time(return_flight2['DepartureTime'])}"},
                    {"type": "text", "text":f"  • {add_durations(r2)}+Layover({destination_return1['LayoverTimeInMinutes']})"},
                    {"type": "text", "text":f"{currency} {flight_data[1]['FareBreakdown']}"}
                    
                    
                    
                    
                    
                    
                ]
            },
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": 
                [
                    {"type": "text", "text": final_url}  # Include the final URL as a button
                ]
            }
        ]
    }
}

    response = requests.post(whatsapp_api_url, headers=headers, json=payload)
    print(response.json())
    
import re

def add_durations(durations):
    """
    Adds multiple duration strings while handling various formats.
    Supports: '1d 2h', '3hrs 5mins', '2d 4hr 50min', etc.
    """

    total_days = 0
    total_hours = 0
    total_minutes = 0

    if isinstance(durations, str):  
        durations = [durations]  # Convert a single string to a list

    for duration in durations:
        # Normalize different formats (hrs → h, mins → m)
        duration = duration.lower().replace("hrs", "h").replace("hr", "h").replace("mins", "m").replace("min", "m")

        # Extract days, hours, and minutes
        days = re.findall(r'(\d+)\s*d', duration)
        hours = re.findall(r'(\d+)\s*h', duration)
        minutes = re.findall(r'(\d+)\s*m', duration)

        # Convert and add to total
        total_days += sum(map(int, days)) if days else 0
        total_hours += sum(map(int, hours)) if hours else 0
        total_minutes += sum(map(int, minutes)) if minutes else 0

    # Convert excess minutes to hours
    total_hours += total_minutes // 60
    total_minutes = total_minutes % 60  # Remaining minutes

    # Convert excess hours to days
    total_days += total_hours // 24
    total_hours = total_hours % 24  # Remaining hours

    # Construct the final formatted string
    formatted_duration = []
    if total_days > 0:
        formatted_duration.append(f"{total_days}d")
    if total_hours > 0:
        formatted_duration.append(f"{total_hours}h")
    if total_minutes > 0:
        formatted_duration.append(f"{total_minutes}m")

    return " ".join(formatted_duration) if formatted_duration else durations 



def format_date(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%b-%Y")

# function to get the country name based on the airport code (you can customize it)

def country_name(city_name):
    base_url=config('AIRPORT_SEARCH_API_URL')
    url= f"{base_url}/airportSearch/{city_name}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        result = data.get('result', [])
        if result:
            Country_Name = result[0].get('Country_Name', '')
            return Country_Name
        else:
            print(f"No country found for {city_name}")
            return None
        
import urllib.parse
# Function to generate the flight URL with "View More" as text
def generate_flight_url(flight_data):
    # Extract details from the flight data
    flight_data = flight_data[0]  # Assuming flight_data is a list of flight info
    origin_destinations = flight_data['OriginDestination']  # List of flight segments
    return_flight = flight_data['return'][0] if 'return' in flight_data else None

    # First Origin
    first_origin = origin_destinations[0]

    # Last Destination (for multi-leg flights)
    last_destination = origin_destinations[-1]  # Get last flight segment

    # Encode origin and destination details
    origin_encoded = urllib.parse.quote(
        json.dumps({
            "Airport_Code": first_origin["OriginCode"],
            "Airport_Name": first_origin["OriginAirportName"],
            "City_name": first_origin["OriginAirportName"].split()[0],
            "Country_Name": country_name(first_origin["OriginCode"])
        })
    )
    
    destination_encoded = urllib.parse.quote(
        json.dumps({
            "Airport_Code": last_destination["DestinationCode"],
            "Airport_Name": last_destination["DestinationAirportName"],
            "City_name": last_destination["DestinationAirportName"].split()[0],  # Extract last city name
            "Country_Name": country_name(last_destination["DestinationCode"])
        })
    )

    # Prepare other parameters
    trip_type = "Round Trip" if return_flight else "One Way"  # Check if return flight exists
    trip_type_encoded = urllib.parse.quote(trip_type)  # Encode the trip type
    adults = 1
    children = 0
    infants = 0
    cabin_class = first_origin["CabinClass"]

    # Format departure and return dates
    departure_date = format_date(first_origin["DepartureTime"].split("T")[0])

    # Construct the URL based on trip type
    if return_flight:
        return_date = format_date(return_flight["DepartureTime"].split("T")[0])
        final_url = (
            f"flights/listing-flights/"
            f"{origin_encoded}/{destination_encoded}/{trip_type_encoded}/"
            f"{adults}/{children}/{infants}/{cabin_class}/"
            f"{departure_date}/{return_date}/0"
        )
    else:
        final_url = (
            f"flights/listing-flights/"
            f"{origin_encoded}/{destination_encoded}/{trip_type_encoded}/"
            f"{adults}/{children}/{infants}/{cabin_class}/"
            f"{departure_date}/0"
        )

    # Return the final URL
    return final_url

def extract_one_way_details(flight_data,to):
    outbound_flight1 = flight_data[0]['OriginDestination'][0]
    outbound_flight2 = flight_data[1]['OriginDestination'][0]
    destination_out=flight_data[0]['OriginDestination'][-1]
    destination_out1=flight_data[1]['OriginDestination'][-1]
    #return_flight1 = flight_data[0]['return'][0]
    #return_flight2 = flight_data[1]['return'][0]
   # destination_return=flight_data[0]['return'][-1]
    #destination_return1=flight_data[1]['return'][-1]
   # print(destination_return1)
    currency = detect_currency(to)
    o1=[segment.get('Duration') for segment in flight_data[0]['OriginDestination']]

    #r1=[segment.get('Duration') for segment in flight_data[0]['return']]
    #r2=[segment.get('Duration') for segment in flight_data[1]['return']]
    o2=[segment.get('Duration') for segment in flight_data[1]['OriginDestination']]


    #print("Return Flight 1 Duration:",flight_data[0]['return'].get('Duration'))
    #print("Outbound Flight 2 Duration:", flight_data[1]['OriginDestination'].get('Duration'))
    #print("Return Flight 2 Duration:", flight_data[1]['return'].get('Duration'))

    final_url=generate_flight_url(flight_data)
    ACCESS_TOKENS= 'EAAIoiNqc3okBO1uIsCdFmFWF9fPH7rgd4ebgfzgRJ1zGONPY7DoVn98exDUdGzfeOsu9dcos8tVCucnxKiIzAPjzUblQ4braEQ9WFn5GwNmOFom4ZB5AxK64RtXCf0r4uNzkWig2HwWsDlHQW5ju0TZCdPnjAyerZBcPRGtmfDpqvNpg2BgGA8RU8KjxlEvywZDZD'
    PHONE_NUMBER_ID = '568728092971072' 
    whatsapp_api_url = f'https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages'
    #to=919500915713
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKENS}",
        "Content-Type": "application/json"
    }

    payload = {
    "messaging_product": "whatsapp",
    "to": to,  # Replace with the recipient's phone number
    "type": "template",
    "template": {
        "name": "oneway",
        "language": {"code": "en_US"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": outbound_flight1['CabinClass']},  # 1 class type
                    {"type": "text", "text": f"{outbound_flight1['OriginCode']} to {destination_out['DestinationCode']}"},  # 2 origin to destination
                    {"type": "text", "text": extract_date(outbound_flight1['DepartureTime'])},  # 3 date
                    {"type": "text", "text": f"{outbound_flight1['OriginCode']} to {destination_out['DestinationCode']} via {outbound_flight1['MarketingAirlineName']}"},#4
                    {"type": "text", "text": f"  • {extract_date(outbound_flight1['DepartureTime'])}@{extract_time(outbound_flight1['DepartureTime'])}"},  # 5date@time
                    {"type": "text", "text": f"  • {add_durations(o1)}+Layover({destination_out['LayoverTimeInMinutes']})"},  # 6 duration total
                    {"type": "text", "text":f"{currency} {flight_data[0]['FareBreakdown']}"},  # 7 total cost
                    {"type": "text", "text": f"{outbound_flight1['OriginCode']} to {destination_out['DestinationCode']} via {outbound_flight2['MarketingAirlineName']}"},#8
                    {"type": "text", "text": f"  • {extract_date(outbound_flight2['DepartureTime'])}@{extract_time(outbound_flight2['DepartureTime'])}"},  # 9 date@time
                    {"type": "text", "text": f"  • {add_durations(o2)}+Layover({destination_out1['LayoverTimeInMinutes']})"},  # 10 total time
                    {"type": "text", "text":f"{currency} {flight_data[1]['FareBreakdown']}"}  # 11 total cost return flight
                ]
            },
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [
                    {"type": "text", "text": final_url}  # Include the final URL as a button
                ]
            }
        ]
    }
}


    response = requests.post(whatsapp_api_url, headers=headers, json=payload)
    print(response.json())