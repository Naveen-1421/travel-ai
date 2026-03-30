import requests
import pandas as pd
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from datetime import datetime, timedelta
#from pulp import LpMaximize, LpProblem, LpVariable, lpSum
import string
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor
import openai
from datetime import date, timedelta
from ortools.linear_solver import pywraplp
from decouple import config
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))
last_city = None  # Initialize last_city as a global variable


def sugg(city=None, msg=None ,hotel_date=None,returndate_out=None):
    global last_city  # Refer to the global variable

    # Handling city logic
    if city is None and last_city is not None:
        city_to_use = last_city
    elif city is not None:
        last_city = city
        city_to_use = city
    else:
        return "No city has been provided yet."

    # Handling msg logic to call different functions
    if msg == "hotel_suggestion":
        #today = date.today()
        #returndate = today + timedelta(days=1)
        #today_in = today.strftime("%Y-%m-%d")
        #returndate_out = returndate.strftime("%Y-%m-%d")
        hotel_sugg = find_hotel_in_city(city_to_use, hotel_date, returndate_out, 1, 1, 1)
        if hotel_sugg:
            return hotel_sugg
        else:
            return "No Hotels available"

    return "No message specified or unsupported message type."



def get_city_code(city):
    #url = f"http://54.226.159.206:3005/api/v1/hotel/destinations?search={city}"
    base_url = config('city_cod')
    url = f"{base_url}?search={city}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json().get('data', [])
        if data:
            city_info = data[0].split(', ')
            city_code = city_info
           
            return city_code 
        else:
            return "hotels not available"# Return None if city code not found
def find_hotel_in_city(origin, checkin_date, checkout_date, no_of_room, no_of_adult, no_of_children):
    today = checkin_date
    return_date = checkout_date
    city_code = get_city_code(origin)
    date_format = "%Y-%m-%d"
    start_date = datetime.strptime(checkin_date, date_format)
    end_date = datetime.strptime(checkout_date, date_format)

# Calculate the difference in days
    number_of_days = (end_date - start_date).days
    url=config('hotel_find')
    # JSON payload
    payload = {
        "stay": {
        "checkIn": checkin_date,
        "checkOut": checkout_date
    },
    "occupancies": [
        {
            "rooms": 1,
            "adults": 2,
            "children": 0,
            "paxes": []
        }
    ],
    "destination": {
        "code": city_code[0]
    },
    "isMRWC": False,
    "filters": {},
    "sortType": "R",
    "hotelName": "",
    "currency": "USD"
    }

    # Make the POST request
    response = requests.post(url, json=payload)

    # Check the response
    if response.status_code == 200:
        data = response.json()

        hotel_table = []  # Define hotel_table outside the if block

        if "Results" in data:
            hotel_table = []
            for hotel in data["Results"][:5]:
                hotel_table.append({
                    'Name': hotel.get("name", "N/A"),
                    'ADDRESS': hotel.get("address", "N/A"),
                    'Price': "${}".format(hotel.get("minRate", "N/A")/number_of_days),
                    'Rating': hotel.get("rating", "N/A"),
                    'Imageurl': hotel.get("images", "N/A")[0],
                    'checkin_date': checkin_date,
                    'checkout_date': checkout_date,
                    "no_of_room": no_of_room,
                    "city_code": city_code[0],
                    "city_name": city_code[1],
                    "state": city_code[2]
                })
        return hotel_table
    else:
        print("Error:", response.status_code)

def airport_code(city_name):
    base_url=config('AIRPORT_SEARCH_API_URL')
    url= f"{base_url}/airportSearch/{city_name}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        result = data.get('result', [])
        if result:
            airport_code = result[0].get('Airport_Code', '')
            return airport_code
        else:
            print(f"No airport found for {city_name}")
            return None
def fetch_flight_booking_details(origin,destination,departure_date, return_date,no_of_adult,no_of_children,no_of_infant):
    if not airport_code(origin ):
        return None
    if not airport_code(destination):
        return None
    url = config('FLIGHT_SEARCH_API_URL')
    data = {
        "JourneyType": "R",
        "ClassType": "E",
        "MultiCityTripdata": [],
        "NoOfAdult": {
            "Count": no_of_adult
        },
        "NoOfChildren": {
            "Count": no_of_children,
            "Age": {}
        },
        "NoOfInfant": {
            "Count": no_of_infant,
            "Age": {}
        },
        "OriginDestination": [
            {
                "Origin": airport_code(origin ),
                "Destination": airport_code(destination),
                "DepartureDate": departure_date
            },
            {
                "Origin": airport_code(destination),
                "Destination":airport_code(origin ),
                "DepartureDate": return_date
            }
        ],
        "OtherInfo": {
            "RequestedIP": "",
            "TransactionId": ""
        },
        "PreferredAirlines": [],
        "PreferredCurrency": "USD"
    }
    response = requests.post(url, json=data)
    s=[]
    if response.status_code == 200:
        result = response.json()
        result_list=[]
        for flight in result.get('result', [])[:1]:
            journey_info_o = flight.get('Itinerary', [])[0].get('JourneyInfo', {})
            journey_info_r=flight.get('Itinerary', [])[1].get('JourneyInfo', {})
            origin_destination = flight.get('Itinerary', [])[0].get('OriginDestination', [])
            od2=flight.get('Itinerary', [])[1].get('OriginDestination', [])
            fare_breakdown = flight.get('FareBreakdown', [])[0].get('GrossFare','')
            destination_airport = origin_destination[-1].get('DestinationAirportName', 'Unknown Destination')
            id = flight.get('IteneraryRefID', "")
            result = {'JourneyInfo_o': journey_info_o,
                      'JourneyInfo_r': journey_info_r,
                      'OriginDestination': origin_destination,
                      'return':od2,
                      'FareBreakdown': fare_breakdown,
                      'ID':id}
            sugg(city=destination_airport)
            result_list.append(result)
    else:
        print("Failed to retrieve data. Status code:", response.status_code)
        print("Error Response:", response.text)
    return result_list

def find_attractions(city, checkin_date, checkout_date):
    city_id, city_name = find_code(city)
    if city_id:
        base_url = config('ATTRACTIONS_API_URL')
        url = f"{base_url}/destinationActivities?destination={city_id}&perPage=100"
        data = {
            "filtering": {
                "startDate": checkin_date,
                "endDate": checkout_date,
                "durationInMinutes": {
             "from": 0,
             "to": 780},

                "attractionId": None
            },
            "sorting": {
                "sort": "DEFAULT"
            },
            "currency": "USD"
        }

        response = requests.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            if 'data' in result:
                attractions_info = result['data']
                data_list = []
                for attraction in attractions_info:
                    product_code = attraction.get('productCode', '')
                    title = attraction.get('title', '')
                    rating = attraction.get('rating', {}).get('averageRating', 0)
                    img_url = attraction.get('imgUrl', '')
                    price = attraction.get('price', 0)
                    description = attraction.get("description", '')
                    duration = attraction.get('duration', '')
                    data_list.append({'Name': title, 'att_description': description, 'code': city_id, 'URL': img_url, 'Price$': price, 'product_code': product_code, 'rating': rating, 'city': city_name, 'duration': duration})
                attraction_data = pd.DataFrame(data_list)
                
                # Convert duration using parse_duration function
                attraction_data['duration'] = attraction_data['duration'].apply(parse_duration)
                
                return attraction_data
            else:
                return pd.DataFrame([])  # Return empty DataFrame if no attractions found
        else:
            return pd.DataFrame([])  # Return empty DataFrame if request fails
    else:
        return pd.DataFrame([])

def find_code(city):
    base_url=config('ATTRACTIONS_CODE')
    url = base_url.format(city)
    response = requests.get(url)
    if response.status_code == 200:
        result = response.json()
        if 'data' in result:
            destination_info = result['data'].get('destination', [])
            if destination_info:
                first_destination_id = destination_info[0].get('id', None)
                city_name = destination_info[0].get('name', None)
                return first_destination_id, city_name
    return None, None


def parse_duration(duration_str):
    # Remove unwanted characters and whitespace
    duration_str = re.sub(r'to', '-', duration_str.lower().replace(' ', ''))
   
    duration_str = re.sub(r'[^0-9hrsminday-]', '', duration_str.lower().replace(' ', ''))
    

    # Convert hours and minutes to hours
    def convert_to_hours(time_str):
        if 'day' in time_str:
            parts = time_str.split('day')
            hours = float(parts[0]) * 24
            return hours
        elif 'hr' in time_str:            
            parts = time_str.split('hr')
            hours = float(parts[0]) if parts[0] else 0
            if len(parts) > 1 and 'min' in parts[1]:
                minutes = float(parts[1].replace('min', '').replace('s', '')) / 60 if parts[1] else 0
                return hours + minutes
            return hours
        elif 'min' in time_str:
            minutes = float(time_str.replace('min', '').replace('s', '')) / 60 if time_str else 0
            return minutes
        return 0

    # If duration is a range
    if '-' in duration_str:
        range_parts = duration_str.split('-')
        try:
            int(range_parts[0])
            if "hr" in range_parts[1]:
                range_parts[0] += "hrs"
            else:
                range_parts[0] += "mins"                  
        except ValueError:
            pass
        start_time = convert_to_hours(range_parts[0])
        end_time = convert_to_hours(range_parts[1])
        return (start_time + end_time) / 2  # Return the average of the range
    else:
        return convert_to_hours(duration_str)
        


def optimize_budget_with_knapsack(attractions, budget):
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        raise Exception("Solver not available")

    # Define variables
    x = {}
    for i, attraction in enumerate(attractions):
        x[i] = solver.IntVar(0, 1, f'attraction_{i}')
    
    # Define objective function: maximize the total value of attractions (e.g., ratings)
    solver.Maximize(solver.Sum([attractions[i]['rating'] * x[i] for i in range(len(attractions))]))

    # Define budget constraint
    solver.Add(solver.Sum([attractions[i]['Price$'] * x[i] for i in range(len(attractions))]) <= budget)

    # Solve the problem
    status = solver.Solve()

    # Get selected attractions
    selected_attractions = [attractions[i] for i in range(len(attractions)) if x[i].solution_value() == 1]
    total_cost = sum(a['Price$'] for a in selected_attractions)
    

    return selected_attractions, total_cost



from datetime import datetime, timedelta

def adjust_date_based_on_time(date_str):
    # Parse the input date string to a datetime object
    date_time = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
    after_day=date_time+timedelta(days=1)
    return after_day.date()

def adjust_date_check_out(date_str):
    # Parse the input date string to a datetime object
    date_time = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
    before_day = date_time + timedelta(days=-1)

    return  before_day.date()
# Example usage
#selected_attractions, total_cost = optimize_budget_with_knapsack(attractions_list, budget)


def generate_schedule(attractions, checkin_date, checkout_date, keyword=None):
    start_date = datetime.strptime(checkin_date, "%Y-%m-%d")
    end_date = datetime.strptime(checkout_date, "%Y-%m-%d")

    # Ensure attractions is a DataFrame
    if not isinstance(attractions, pd.DataFrame):
        raise ValueError("Expected 'attractions' to be a DataFrame")

    # Initialize schedule dictionary
    schedule = {}
    current_day = start_date
    scheduled_attractions = set()  # To track already scheduled attractions

    # Sorting attractions by cosine similarity if keyword is provided
    if keyword:
        attractions = attractions.sort_values(by='cosine_similarity', ascending=False)

    # Remove duplicates from attractions based on product_code
    attractions = attractions.drop_duplicates(subset=['product_code'])

    # Group attractions by duration categories
    one_day_attractions = attractions[(attractions['duration'] >= 8)&(attractions['duration']<=12)]
    twelve_hour_attractions = attractions[(attractions['duration'] < 8) & (attractions['duration'] >= 4)]
    three_hour_attractions = attractions[(attractions['duration'] < 4) & (attractions['duration'] >= 2)]
    one_hour_attractions = attractions[attractions['duration'] < 2]

    # Assign one-day attractions (one per day)
    for i in range(len(one_day_attractions)):
        if current_day > end_date:
            break
        day_attractions = one_day_attractions.iloc[i:i+1]  # Select 1 attraction for the current day
        day_schedule = [row.to_dict() for _, row in day_attractions.iterrows()]
        schedule[current_day.date().isoformat()] = day_schedule  # Add day's schedule to dictionary
        scheduled_attractions.update(day_attractions.index)  # Mark attractions as scheduled
        current_day += timedelta(days=1)  # Move to the next day

    # Assign remaining attractions with a limit of 3 per day
    remaining_attractions = attractions[~attractions.index.isin(scheduled_attractions)]
    day_schedule = []
    while current_day <= end_date:
        day_schedule = []
        for _, row in remaining_attractions.iterrows():
            if len(day_schedule) < 3:
                day_schedule.append(row.to_dict())
                scheduled_attractions.add(row.name)  # Mark attraction as scheduled
            if len(day_schedule) == 3:
                break
        schedule[current_day.date().isoformat()] =day_schedule
        current_day += timedelta(days=1)
        remaining_attractions = attractions[~attractions.index.isin(scheduled_attractions)]

    # Calculate the total cost of attractions in the schedule
    total_cost = 0
    for day, activities in schedule.items():
        for activity in activities:
            total_cost += activity['Price$']

    return schedule, total_cost
def schedule_details(origin,destination,checkin_date,checkout_date):
    with ThreadPoolExecutor() as executor:
        flight=executor.submit(fetch_flight_booking_details,origin, destination, checkin_date, checkout_date, 1, 0, 0)
        hotel=executor.submit(sugg,city=destination, msg="hotel_suggestion",hotel_date=checkin_date,returndate_out=checkout_date)
        e=executor.submit(find_attractions,destination, checkin_date, checkout_date)
        a=flight.result()
        b=hotel.result()
        attraction_data=e.result()
    return a,b,attraction_data

def attraction_schedule(attractions_list,budget,checkin_date, checkout_date):
    selected_attractions, total_cost = optimize_budget_with_knapsack(attractions_list, budget) 
    schedule, total_cost = generate_schedule(pd.DataFrame(selected_attractions), checkin_date, checkout_date, keyword=None)
    schedule = {date: activities for date, activities in schedule.items() if activities}
    return schedule,total_cost 
