import nltk
import json
from nltk.stem import WordNetLemmatizer
import pickle
import numpy as np
from keras.models import load_model 
lemmatizer = WordNetLemmatizer()
#nltk.download('punkt')
#nltk.download('wordnet')
model = load_model('mymodel.h5')
intents = json.loads(open('intent.json').read())
words = pickle.load(open('words.pkl', 'rb'))
classes = pickle.load(open('classes.pkl', 'rb'))


def clean_up(sentence):
    sentence_words = nltk.word_tokenize(sentence)
    sentence_words = [lemmatizer.lemmatize(word.lower()) for word in sentence_words]
    return sentence_words
def create_bow(sentence, words):
    sentence_words = clean_up(sentence)
    bag = list(np.zeros(len(words)))

    for s in sentence_words:
        for i, w in enumerate(words):
            if w == s:
                bag[i] = 1
    return np.array(bag)
def predict_class(sentence, model):
    p = create_bow(sentence, words)
    res = model.predict(np.array([p]))[0]
    threshold = 0.8
    results = [[i, r] for i, r in enumerate(res) if r > threshold]
    results.sort(key=lambda x: x[1], reverse=True)
    return_list = []
    for result in results:
        return_list.append({'intent': classes[result[0]], 'prob': str(result[1])})
    return return_list