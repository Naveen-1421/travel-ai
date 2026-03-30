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
from subclass import extract_hotel_details_n,book_hotel,suggest_hotels
from conversation import build_next_suggestions, handle_flight_flow,handle_hotel_flow
from url import normalize_hotels,add_travelfika_links
from flask_cors import CORS
from packages import recommend_packages,hard_filter_destination
from pymongo import MongoClient
import speech_recognition as sr
import soundfile as sf
import io
from aitriplanner import full_attraction
from concurrent.futures import ThreadPoolExecutor
import inflect
from whatsapp import attractiontemplate,detect_currency,extract_round_trip_details,extract_one_way_details
from whatsapp import hoteltemplate,identify_response_type
from suggestion import generate_user_input_suggestions
from travel_advisor import generate_response 
CHATBOT_API_URL = config("CHATBOT_API")
ACCESS_TOKEN = config("ACCESS_TOKENS")
PHONE_NUMBER_ID =config("NUMBER_ID")
VERIFY_TOKEN =config("VERIFY_TOKENS")
# -------------------- APP SETUP --------------------
app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "http://54.226.159.206:8888", "http://tf-frontend-web.s3-website-us-east-1.amazonaws.com", "https://www.travelfika.com","http://54.226.159.206:8844","https://crm.travelfika.com"])
db_client = MongoClient('mongodb+srv://travel_fika_tfcluster0:F3qTnukosB0KiYSM@cluster0.fzzlv7i.mongodb.net/?')
#db_client=''
db = db_client['whatsapp_chat']
chat_history_collection1 = db["chat_history"]
messages_collection = db["messages"]
openai.api_key = config("openai")

nlp = spacy.load("en_core_web_sm")

# -------------------- LOAD MODELS --------------------
model = load_model("mymodel.h5")

ner_model = pipeline(
    "ner",
    model="dbmdz/bert-large-cased-finetuned-conll03-english",
    aggregation_strategy="simple"
)

intents = json.loads(open("intent.json").read())
conversation = {}
gpt_memory = {}   # GPT conversation memory per chat_id


ANAH_SYSTEM_PROMPT = """
You are Anah, an intelligent travel assistant.

Rules:
- Remember previous user context
- Be concise and accurate
- Use travel data realistically
- Ask clarifying questions only if required
- Never expose internal reasoning
"""

def get_gpt_history(chat_id):
    if chat_id not in gpt_memory:
        gpt_memory[chat_id] = [
            {"role": "system", "content": ANAH_SYSTEM_PROMPT}
        ]
    return gpt_memory[chat_id]


def save_gpt_history(chat_id, history, max_len=12):
    gpt_memory[chat_id] = history[-max_len:]


# -------------------- GPT FALLBACK --------------------
def get_gpt_response(question, user_id, city=None, extra_context=None):
    history = get_gpt_history(user_id)

    # Inject city context (once per turn)
    if city:
        history.append({
            "role": "system",
            "content": f"User is currently interested in {city}."
        })

    # Inject grounded data if available
    if extra_context:
        history.append({
            "role": "system",
            "content": extra_context
        })

    # Add user message
    history.append({
        "role": "user",
        "content": question
    })

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=history,
        temperature=0.6,
        max_tokens=800
    )

    reply = response.choices[0].message["content"]

    # Save assistant reply
    history.append({
        "role": "assistant",
        "content": reply
    })

    save_gpt_history(user_id, history)

    return reply


def parse_flight_query(text):
    data = {
        "origin": None,
        "destination": None,
        "departure_date": None,
        "return_date": None,
        "journeytype": "O"
    }
    cities = [ent.text for ent in nlp(text).ents if ent.label_ in ["GPE", "LOC"]]

    if len(cities) >= 2:
        data["origin"] = cities[0]
        data["destination"] = cities[1]
    elif len(cities) == 1:
        data["destination"] = cities[0]
    lower = text.lower()
    if "round" in lower or "return" in lower:
        data["journeytype"] = "R"
    dates = extract_dates(text)
    if dates:
        data["departure_date"] = dates.get("start_date")
        data["return_date"] = dates.get("end_date")
    return data

# -------------------- MISSING FIELDS --------------------
def get_missing_flight_fields(parsed):
    missing = []
    if not parsed.get("origin"):
        missing.append("origin")
    if not parsed.get("destination"):
        missing.append("destination")
    if not parsed.get("departure_date"):
        missing.append("departure_date")
    if parsed.get("journeytype") == "R" and not parsed.get("return_date"):
        missing.append("return_date")
    return missing
# -------------------- START CONVERSATION FLOW --------------------
def start_flight_flow(chat_id):
    conversation[chat_id] = {
        "booking_flight": True,
        "origin": None,
        "destination": None,
        "journey_type": None,
        "depart_date": None,
        "return_date": None
    }
def get_response(return_list, intents_json, text, user_id, city, currency):

    if not return_list or return_list[0]['intent'] in ["general", "trip_planner"]:

        gpt_text = get_gpt_response(text, user_id, city)
        # ✅ Extract destination from USER input
        destination =  extract_destination(gpt_text)
        link_text =add_travelfika_links(gpt_text)
        #print("🔗 Link text:", link_text)
        flights = []  # ✅ FIX: initialize early

        # 🟥 Destination found but origin missing
        if destination and not city:
            return {
                "responses": link_text,
                "ask_origin": True,
                "message": "✈️ I can also help you with flights. Which city are you departing from?",
                "destination": destination,
                "currency": currency
            }, None

        # 🟩 Destination + origin available → fetch flights
        if destination and city:
            try:
                flights = suggest_flights(city, destination, currency)
                hotel = suggest_hotels(destination, currency)
            except Exception as e:
                print("✈️ Flight error:", e)

            return {
                "responses":link_text,
                "flights": flights,
                "origin": city,
                "destination": destination,
                "hotels":hotel,
                "currency": currency
            }, None

        # 🟨 Only itinerary (NO flights)
        return {
            "responses": link_text,
            "currency": currency,
            "next_suggestions": build_next_suggestions("general", {})
        }, None
    # -------- FLIGHT FLOW --------
    tag = return_list[0]['intent']
    #print("🎯 INTENT:", tag)

    if tag in ['book_flight', 'manual_flight']:

        extracted_details = extract_travel_details(tag, text, currency)
        flight_info = extracted_details.get("flight", {})

        if isinstance(flight_info, dict) and "message" in flight_info:
            conversation.setdefault(user_id, {})
            conversation[user_id]["booking_flight"] = True
            return flight_info["message"], None

        if flight_info:
            flight_data = book_flight(flight_info)
            if flight_data:
                conversation.pop(user_id, None)
                return flight_data, None

        conversation.setdefault(user_id, {})
        conversation[user_id]["booking_flight"] = True
        response, _ = handle_flight_flow(user_id, text, currency)
        #conversation.pop(user_id, None)
        return response, None
    if tag in ['book_hotel', 'manual_hotel']:
        extracted_details = extract_travel_details(tag, text, currency)
        hotel_info = extracted_details.get("hotel", {})

        if isinstance(hotel_info, dict) and "message" in hotel_info:
            conversation.setdefault(user_id, {})
            conversation[user_id]["booking_hotel"] = True
            return hotel_info["message"], None

        if hotel_info:
            hotel_data = book_hotel(hotel_info)
            if hotel_data:
                conversation.pop(user_id, None)
                return hotel_data, None

        conversation.setdefault(user_id, {})
        conversation[user_id]["booking_hotel"] = True
        response, _ = handle_hotel_flow(user_id, text, currency)
        return response, None
    if tag in ['packages']:
        packages = recommend_packages(text,currency="INR",budget=None,travel_date=None,top_k=5)
        return packages, None
    # -------- STATIC INTENTS --------
    for intent in intents_json['intents']:
        if tag == intent['tag'] and intent.get('responses'):
            return random.choice(intent['responses']), None

    # -------- SAFE FALLBACK --------
    return get_gpt_response(text, user_id, city), None

# -------------------- CHAT ROUTE --------------------
def save_chat_history(user_id, chat_id, message, bot_response, currency):
    chat_entry = {
        'chat_id': chat_id,
        'timestamp': datetime.now(),
        'user_message': message,
        'bot_response': bot_response,
        'currency': currency
    }

    chat_history_collection1.update_one(
        {'user_id': user_id, 'chat_id': chat_id},
        {
            '$push': {'chat_history': chat_entry},
            '$setOnInsert': {
                'user_id': user_id,
                'chat_id': chat_id,
                'title': message,
                'created_at': datetime.now()
            }
        },
        upsert=True
    )

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    chat_id = data.get("chat_id")
    message = data.get("message")
    user_id = data.get("user_id")
    currency = data.get("currency", "INR")
    city = data.get("city")

    if not chat_id or not message:
        return jsonify({"error": "chat_id and message are required"}), 400

    conversation.setdefault(chat_id, {})

    # 🔄 Reset
    if message.lower() in ["reset", "cancel"]:
        conversation.pop(chat_id, None)
        return jsonify({"responses": "Conversation reset."})

    # ✈️ LOCKED FLIGHT FLOW
    if conversation[chat_id].get("booking_flight"):
        res, _ = handle_flight_flow(chat_id, message, currency)
        save_chat_history(user_id, chat_id, message, res, currency)

        #print("Flight flow response:", res)
        #print("Flight flow response:", res)
        if isinstance(res, dict) and res.get("data"):
            conversation.pop(chat_id, None)
        return jsonify(res)
    
    if conversation[chat_id].get("booking_hotel"):
        res, _ = handle_hotel_flow(chat_id, message, currency)
        save_chat_history(user_id, chat_id, message, res, currency)
        if isinstance(res, dict) and res.get("data"):
            conversation.pop(chat_id, None)
        return jsonify(res)
    
    return_list = predict_class(message, model)

    bot_response, final_message = get_response(return_list,intents,message,chat_id,city,currency)
    #print("Bot response:", bot_response)
    chat_entry = {
        'chat_id': chat_id,
       'timestamp': datetime.now(),
        'user_message': message,
        'bot_response': bot_response,
        'currency': currency # Save the current conversation state
       }
    chat_history_collection1.update_one(
    {'user_id': user_id, 'chat_id': chat_id},
    {
     
        '$push': {'chat_history': chat_entry},
       '$setOnInsert': {
            'user_id': user_id,
            'chat_id': chat_id,
           'title': message,
            'created_at': datetime.now()
        }
    },
    
    
    upsert=True

)

    if final_message:
        return jsonify(final_message)

    if isinstance(bot_response, dict):
       return jsonify(bot_response)
    
    return jsonify({
        "responses": bot_response,
        "currency": currency
    }) 
@app.route('/recognize_speech', methods=['POST'])
def recognize_speech():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'})

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': 'No audio file selected'})
    r = sr.Recognizer()

    try:
        audio_content = io.BytesIO(audio_file.read())

        file_extension = audio_file.filename.lower().split('.')[-1]
        if file_extension == 'wav':
            with sr.AudioFile(audio_content) as source:
                audio = r.record(source)
        else:
            # Convert audio to WAV format
            audio_segment, samplerate = sf.read(audio_content)
            audio_data = audio_segment.astype('float32')

            with io.BytesIO() as wav_io:
                sf.write(wav_io, audio_data, samplerate, format='WAV')
                wav_io.seek(0)
                with sr.AudioFile(wav_io) as source:
                    audio = r.record(source)  

        text = r.recognize_google(audio)
        return jsonify({'text': text})
    except sr.UnknownValueError:
        return jsonify({'error': 'Unable to recognize speech'})
    except sr.RequestError as e:
        return jsonify({'error': 'Error occurred with the speech recognition service: {}'.format(e)})
@app.route('/chat_history', methods=['GET'])
def get_chat_entries():
    try:
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({'error': 'user_id is required'}), 400

        chat_entries = chat_history_collection1.find(
            {'user_id': user_id},
            {'chat_history': 1,'title':1}
        )

        chat_history_dict = {}
        for chat_entry in chat_entries:
            for entry in chat_entry['chat_history']:
                title_limited = chat_entry.get('title', '')[:30] 
                chat_id = entry['chat_id']
                timestamp = entry['timestamp']
                message_objects = []
                
                message_objects.append({'author': 'author', 'message': entry['user_message']})
                message_objects.append({'author': 'assistant', 'message': entry['bot_response']})
                
                if chat_id in chat_history_dict:
                    chat_history_dict[chat_id]['messages'].extend(message_objects)
                    chat_history_dict[chat_id]['end_time'] =entry['timestamp']
                else:
                    chat_history_dict[chat_id] = {'title': title_limited,'chatId': chat_id, 'messages': message_objects,'start_time':timestamp}

        return jsonify( list(chat_history_dict.values()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500 
@app.route('/update_title', methods=['PATCH'])
def update_title():
    try:
        user_id = request.args.get('user_id')
        chat_id = request.args.get('chat_id')
        new_title = request.args.get('new_title')

        chat_history_collection1.update_one(
            {'user_id': user_id, 'chat_id': chat_id},
            {'$set': {'title': new_title}}
        )

        return jsonify({'message': 'Title updated successfully'})
    
    except Exception as e:
        return jsonify({'error': str(e)})
@app.route('/delete_chat', methods=['DELETE'])
def delete_chat():
    user_id = request.args.get('user_id')
    chat_id = request.args.get('chat_id')

    if not user_id or not chat_id:
        return jsonify({'error': 'Missing user_id or chat_id'}), 400

    result = chat_history_collection1.delete_one({'user_id': user_id, 'chat_id': chat_id})

    if result.deleted_count:
        return jsonify({'message': 'Chat deleted successfully'}), 200
    else:
        return jsonify({'error': 'Deletion failed'}), 404

@app.route('/delete_all', methods=['DELETE'])
def delete_entire():
    user_id = request.args.get('user_id')

    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400

    result = chat_history_collection1.delete_many({'user_id': user_id})

    if result.deleted_count:
        return jsonify({'message': 'entire Chat deleted successfully'}), 200
    else:
        return jsonify({'error': 'Deletion failed'}), 404   
    
@app.route('/ai_attractions', methods=['POST'])
def trip_planner():
    data = request.json
    destination = data.get("destination")
    num_days =data.get("num_days")
    destinationID=data.get("destinationID")
    keyword = data.get("keyword")
    currency=data.get('currency',"USD")
    with ThreadPoolExecutor() as executor:
         e=executor.submit(full_attraction,destination,num_days,keyword,destinationID,currency=currency)
         attraction_data,r,d,destination_id,destination_name=e.result()
    total_days=num_days
    p = inflect.engine()
    total_days_in_words = p.number_to_words(total_days)
    result = {
            "attraction":attraction_data,
            "remaining_attraction":r,
            "no_of days":total_days, 
            "tripsummary":d,
            "text_format":total_days_in_words,
            "destination_id":destination_id,
            "destination_name":destination_name
        }

    return jsonify(result)
@app.route('/travel_advisor', methods=['POST'])
def travel_advisor():
    data = request.get_json()
    user_id = data.get("user_id")  # Get the user_id from the request data
    user_input = data.get("user_input")
    query_type = data.get("query_type")
    category = data.get("category")  # Category for thematic queries

    if not user_id or not user_input or not query_type:
        return jsonify({"error": "Both 'user_id', 'user_input', and 'query_type' are required."}), 400

    # Generate and return the response as Rich Text (HTML)
    response = generate_response(user_id, user_input, query_type, category)
    return response

step = {}
PACKAGE_QUESTIONS = [
    ("destination", "Which city or destination are you interested in?"),
    ("start_date", "What is your preferred start date? (MM/DD/YYYY) and no of days"),
    ("travelers", "How many travelers will be going?"),
    ("budget", "What is your budget for the package? (in your currency)?")
]
@app.route("/whatsapp_webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Invalid verification token", 403

    if request.method == "POST":
        incoming_message = request.json
        try:
            entry = incoming_message.get("entry", [])
            if not entry or not isinstance(entry, list):
                raise ValueError("'entry' must be a non-empty list")

            changes = entry[0].get("changes", [])
            if not changes or not isinstance(changes, list):
                raise ValueError("'changes' must be a non-empty list")

            value = changes[0].get("value", {})
            if "statuses" in value:
                statuses = value["statuses"]
                for status in statuses:
                    wamid = status.get("id")
                    message_status = status.get("status")  # sent, delivered, read, failed
                    recipient_id = status.get("recipient_id")
                    timestamp = status.get("timestamp")

                    # ✅ Update DB or log the status
                    result = messages_collection.update_one(
                        {"wamid": wamid},
                        {"$set": {
                            "status": message_status,
                            "statusTimestamp": timestamp,
                            "updatedAt": current_time_iso_ist()
                        }}
                    )

                    #print(f"✅ Message {wamid} to {recipient_id} is now '{message_status}'")
                return "Status received", 200
            messages = value.get("messages", [])
            if not messages or not isinstance(messages, list):
                raise ValueError("'messages' must be a non-empty list")

            msg = messages[0]
            user_phone_number = msg.get("from", None)
            user_message = None

            # ✅ Handle text messages
            if msg.get("type") == "text":
                user_message = msg.get("text", {}).get("body", None)

            # ✅ Handle quick reply button clicks
            elif msg.get("type") == "button":
                user_message = msg.get("button", {}).get("text", None)
                button_payload = msg.get("button", {}).get("payload", None)
                print(f"User clicked button: {user_message}, payload: {button_payload}")
                messages_collection.insert_one({
                     "direction": "incoming",
                     "phoneNumber": user_phone_number,
                     "content": {
                      "type": "text",
                      "text": user_message,
                     "payload": button_payload
                     },
                    "createdAt": current_time_iso_ist(),
                "status": "delivered"
                                     })
                step[user_phone_number] = {
                       "flow": "package",
                        "answers": {},
                        "next_index": 0
                       }
                # send first question
                send_whatsapp_message(user_phone_number, PACKAGE_QUESTIONS[0][1])
                save_outgoing_message(user_phone_number, PACKAGE_QUESTIONS[0][1])
                return "OK", 200 
            # Continue package flow if user is in package
            if user_phone_number in step and step[user_phone_number]["flow"] == "package":
                user_step = step[user_phone_number]
                next_index = user_step["next_index"]

                # store answer for current question
                if next_index < len(PACKAGE_QUESTIONS):
                    question_key, _ = PACKAGE_QUESTIONS[next_index]
                    user_step["answers"][question_key] = user_message
                    user_step["next_index"] += 1
                    # send next question or finish
                if user_step["next_index"] < len(PACKAGE_QUESTIONS):
                    _, next_question = PACKAGE_QUESTIONS[user_step["next_index"]]
                    send_whatsapp_message(user_phone_number, next_question)
                    save_outgoing_message(user_phone_number, next_question)
                else:
                    # all questions answered
                    final_answers = "Travel deals coming your way"
                    send_whatsapp_message(
                        user_phone_number,
                        final_answers
                    )
                    save_outgoing_message(user_phone_number, final_answers)
                    # remove phone number from step to reset flow
                    del step[user_phone_number]

            if not user_message or not user_phone_number:
                raise ValueError("Message text/button or 'from' field is missing")

            # Example: Save message into DB
            messages_collection.insert_one({
                "direction": "incoming",
                "phoneNumber": user_phone_number,
                "content": {
                    "type": msg.get("type"),
                    "text": user_message
                },
                "createdAt": current_time_iso_ist(),
                "status": "delivered"
            })

        except (KeyError, ValueError) as e:
            print(f"Error processing incoming message: {str(e)}")
            print(f"Incoming message: {incoming_message}")
            return "Invalid payload", 400

        return "OK", 200
def save_outgoing_message(phone_number, message_text):
    messages_collection.insert_one({
        "direction": "outgoing",
        "phoneNumber": phone_number,
        "content": {
            "type": "text",
            "text": message_text
        },
        "createdAt": current_time_iso_ist(),
        "status": "sent"  # you can update later if needed
    })


def send_whatsapp_message(to, message):
    # WhatsApp API URL to send messages
    print("Preparing to send message...")

    if isinstance(message, list):
        # Format list into a human-readable string with key names and bullet points
        currency = detect_currency(to)
        message=identify_response_type(message,currency)
    elif isinstance(message, dict):
        currency = detect_currency(to)
        message= identify_response_type(message,currency)
        #print(identify_response_type(message))
        
    # If message is not a string, convert it to a string
    elif not isinstance(message, str):
        message = str(message)  # Convert any other non-string type to a string
    elif isinstance(message, str):
            message = html2text.html2text(message)

    

    #print(f"Message to send: {message}")

    # WhatsApp API URL for sending messages
    url = f'https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages'
    
    # Set the Authorization header with your Access Token
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # Prepare the message payload
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {
            "body": message  # The message is sent as a string inside the 'body' key of 'text'
        }
    }

    # Send the message to WhatsApp
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        print(f"Error sending message: {response.status_code} - {response.text}")
    #else:
        #print(f"Message sent to {to}: {message}")
def current_time_iso_ist():
    """
    Returns current time in ISO 8601 format (IST timezone, UTC+5:30)
    Example: 2025-10-10T10:15:30+05:30
    """
    ist_offset = timedelta(hours=5, minutes=30)
    ist = timezone(ist_offset)
    now_ist = datetime.now(ist)
    return now_ist.replace(microsecond=0).isoformat()

@app.route('/predict_promt', methods=['POST'])  
def predict():
    # Get user query from POST request
    data = request.get_json()
    user_query = data.get("query", "")
    currency = data.get("currency", "")
    userInput=data.get("userInput","")

    if not user_query:
        return jsonify({"error": "Query not provided"}), 400

    # Generate the slot predictions
    slot_suggestions = generate_user_input_suggestions(user_query,currency,userInput)

    return jsonify({"slot_suggestions": slot_suggestions})

@app.route("/api/messages-list", methods=["GET"])
def get_messages():
    msgs = list(messages_collection.find().sort("createdAt", 1))
    # Convert ObjectId to string
    for m in msgs:
        m["_id"] = str(m["_id"])
    return jsonify({"messages": msgs})  
@app.route("/api/messages", methods=["POST"])
def save_message():
    data = request.json
    data["createdAt"] = current_time_iso_ist()
    messages_collection.insert_one(data)
    return jsonify({"status": "ok"})

@app.route("/api/messages/mark-seen", methods=["POST"])
def mark_seen():
    try:
        data = request.json
        phone_number = data.get("phoneNumber")

        if not phone_number:
            return jsonify({"error": "phoneNumber is required"}), 400

        # 🔹 Update all incoming messages for this phone number that are not already seen
        result = messages_collection.update_many(
            {"phoneNumber": phone_number, "direction": "incoming", "status": {"$ne": "seen"}},
            {
                "$set": {
                    "status": "read",
                    "seenAt": current_time_iso_ist()
                }
            }
        )

        if result.matched_count == 0:
            return jsonify({"error": "No messages found to mark as seen"}), 404

        return jsonify({"success": True, "phoneNumber": phone_number, "updatedCount": result.modified_count})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=config('PORT'))   













