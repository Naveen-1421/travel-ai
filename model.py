import json
import keras
import nltk
import pickle
import numpy as np
import random
from nltk.stem import WordNetLemmatizer
from keras.models import Sequential, load_model
from keras.layers import Dense, Dropout
import spacy
nlp = spacy.load("en_core_web_sm")


lemmatizer = WordNetLemmatizer()    
words = []
classes = []
documents = [] 
ignore = ['?', '!', ',', 's']

# Load intents from a JSON filecd
data_file = open('intent.json').read()
intents = json.loads(data_file)
def remove_destinations(text):
    doc = nlp(text)
    filtered_words = []
    for token in doc:
        # Ignore named entities labeled as GPE (cities, countries, locations)
        if token.ent_type_ != "GPE":
            filtered_words.append(token.text)
    return filtered_words
# Preprocess and tokenize data for training
for intent in intents['intents']:
    for pattern in intent['patterns']:

        w = remove_destinations(pattern)
        if not w:
            continue
        words.extend(w)
        documents.append((w, intent['tag']))

        if intent['tag'] not in classes:
            classes.append(intent['tag'])

# Lemmatize and clean words
words = [lemmatizer.lemmatize(word.lower()) for word in words if word not in ignore]
words = sorted(list(set(words)))
classes = sorted(list(set(classes)))

# Save preprocessed data to files
pickle.dump(words, open('words.pkl', 'wb'))
pickle.dump(classes, open('classes.pkl', 'wb'))

# Training data preparation
training = []
output_empty = [0] * len(classes)
max_words = len(words)

for doc in documents:
    bag = [0] * max_words
    pattern_words = doc[0]
    pattern_words = [lemmatizer.lemmatize(word.lower()) for word in pattern_words]

    for w in pattern_words:
        if w in words:
            bag[words.index(w)] = 1

    output_row = list(output_empty)
    output_row[classes.index(doc[1])] = 1
    training.append([bag, output_row])

random.shuffle(training)
X_train = np.array([item[0] for item in training])
y_train = np.array([item[1] for item in training])

# Model definition and training
model = Sequential()
model.add(Dense(64, activation='relu', input_shape=(len(X_train[0]),)))
model.add(Dropout(0.4))
model.add(Dense(32, activation='relu'))
model.add(Dense(32, activation='relu'))
model.add(Dropout(0.4))
model.add(Dense(len(y_train[0]), activation='softmax'))

adam = keras.optimizers.Adam(0.001)
model.compile(optimizer=adam, loss='categorical_crossentropy', metrics=['accuracy'])
weights = model.fit(np.array(X_train), np.array(y_train), epochs=200, batch_size=4, verbose=1)
model.save('mymodel.h5', weights)
loaded_model = load_model('mymodel.h5')