from flask import Flask, request, jsonify
import requests
from datetime import datetime, timedelta
import random
from decouple import config
app = Flask(__name__)

def find_attractions(city_id, checkin_date, checkout_date):
    city_id, city_name = find_code(city_id)
    if city_id:
        base_url = config('ATTRACTIONS_API_URL')
        url = f"{base_url}/destinationActivities?destination={city_id}&page=1"
        print(url)
        data = {
            "startDate": checkin_date, 
            "endDate": checkout_date
        }

        response = requests.post(url, data=data)
        
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
                    duration = attraction.get('duration', 0)
                    data_list.append({'Name': title, 'code': city_id, 'URL': img_url, 'Price$': price, 'product_code': product_code, 'rating': rating, 'city': city_name, 'duration': duration})
                
                return data_list  # Return list of attractions
            else:
               return []  # Return empty list if no attractions found
        else:
            return []  # Return empty list if request fails
    else:
        return []  # Return empty list if city_id is invalid


def find_code(city):
    base_url =config("ATTRACTIONS_CODE")
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

def split_attractions(attractions, checkin_date, checkout_date):
    def get_unique_attraction(attractions, used_attractions):
        for a in attractions:
            if a['Name'] not in used_attractions:
                return a
        return None

    # Convert check-in and check-out dates to datetime objects
    check_in_date = datetime.strptime(checkin_date, '%Y-%m-%d')
    check_out_date = datetime.strptime(checkout_date, '%Y-%m-%d')

    # Initialize variables
    current_date = check_in_date
    day_number = 1
    day_attractions = {}

    # Track used attractions across all days
    used_attractions = set()

    while current_date <= check_out_date:
        day_attractions[current_date.strftime('%Y-%m-%d')] = {'morning': None, 'afternoon': None, 'evening': None}

        # Shuffle attractions for each day to randomize selection
        random.shuffle(attractions)

        for time_slot in ['morning', 'afternoon', 'evening']:
            # Select the next attraction that hasn't been used yet
            attraction = get_unique_attraction(attractions, used_attractions)

            if attraction is not None:
                # Mark attraction as used
                used_attractions.add(attraction['Name'])
                day_attractions[current_date.strftime('%Y-%m-%d')][time_slot] = attraction

        # Move to the next day
        day_number += 1
        current_date += timedelta(days=1)

    return day_attractions