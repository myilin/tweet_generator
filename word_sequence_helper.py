import os
import sys

import numpy as np
from nltk.tokenize import TweetTokenizer
from scipy.spatial import distance
from matplotlib import pyplot

from tweets_helper import getTweets
from filesystem_helper import getDataPath

sys.path.insert(0, '../glove_twitter_tokenizer')
import preprocess_twitter

class WordSequenceProvider:
    def initialize(self, full_text):
        self.vec_len = 26
        print('Indexing word vectors.')
        self.embeddings_index = {}
        #self.embeddings_words = []
        with open('D:\\glove.twitter.27B\\glove.twitter.27B.25d.txt', encoding="utf-8") as f:
            max_count = 1000
            count = 0
            max_value = -100.0
            min_value = 100.0
            wrong_sized = 0
            for line in f:
                values = line.split()
                word = values[0]
                #embeddings_words.append(word)
                coefs = np.asarray(values[1:]+[0.0], dtype='float32')
                if(len(coefs) != self.vec_len):
                    wrong_sized += 1
                    continue
                self.embeddings_index[word] = coefs
                
                max_value = max(max_value, max(coefs))
                min_value = min(min_value, min(coefs))
                
                count += 1
                #if(count > max_count):
                #    break
            
            print("min: " + str(min_value))
            print("max: " + str(max_value))
            print("wrong size: " + str(wrong_sized))

            norm = (max_value - min_value)/2.0

            normalized_embeddings = {}

            for word, coefs in self.embeddings_index.items():
                normalized_embeddings[word] = (coefs - min_value)/norm - 1.0

            self.embeddings_index = normalized_embeddings

        all_values = []
        for word, coefs in self.embeddings_index.items():
            all_values.extend(coefs)
        
        pyplot.hist(all_values, bins=20)
        pyplot.savefig(getDataPath() + "dist_normed")
        pyplot.clf()

        eot_vec = np.zeros(self.vec_len, dtype='float32')
        eot_vec[-1] = 1.0
        self.embeddings_index['<eot>'] = eot_vec

        self.unknown_vec = np.zeros(self.vec_len, dtype='float32')
        self.unknown_vec[-1] = 1.0

        print('Found %s word vectors.' %len(self.embeddings_index))

    def getSequences(self, text, maxlen):
        tokens = self.tokenize(text)

        token_vectors = self.vectorize(tokens, True)

        x = np.zeros((len(token_vectors), maxlen, self.vec_len), dtype='float32')
        y = np.zeros((len(token_vectors), self.vec_len), dtype='float32')

        step = 1

        for i in range(0, len(token_vectors) - maxlen, step):
            x[i] = token_vectors[i: i + maxlen]
            y[i] = token_vectors[i + maxlen]

        return x, y

    def vectorize(self, tokens, verbose=False):
        if(verbose):
            print('Vectorization...')

        unknown_words_count = 0
        for token in tokens:
            if (token not in self.embeddings_index):
                unknown_words_count += 1

        if(verbose):
            print('Found %s unknown tokens' %unknown_words_count)
            print('Miss rate: %f' %(unknown_words_count/len(tokens)))

        token_vectors = np.zeros((len(tokens)-unknown_words_count, self.vec_len), dtype='float32')

        token_id = 0
        for token in tokens:
            if (token in self.embeddings_index):
                token_vectors[token_id] = np.array(self.embeddings_index[token])
                token_id += 1

        if(verbose):
            print('Found %s valid words' %token_id)

        return token_vectors

    def tokenize(self, text):
        #print('Tokenizing text (%s characters)' %len(text))

        text = text.replace('\n---\n', " <eot> ")
        text = preprocess_twitter.tokenize(text)
        text = text.replace("<<", "<").replace(">>", ">")

        tknzr = TweetTokenizer(preserve_case=False, reduce_len=True, strip_handles=True)
        tokens = tknzr.tokenize(text)

        #print('Found %s tokens' %len(tokens))
        return tokens

    def generateText(self, model, seed_sentence, generated_text_size, maxlen, temperature=1.0):
        generated = []
        sentence = self.tokenize(seed_sentence)[0:maxlen]
        generated += sentence

        all_values = []

        for i in range(generated_text_size):
            print(sentence)
            x_pred = self.vectorize(sentence)
            preds = model.predict(np.array([x_pred]), verbose=0)[0]
            print(preds)
            all_values.extend(preds)
            next_token = self.findClosestWord(preds)
            print(next_token)
            
            generated.append(next_token)
            sentence = sentence[1:] + [next_token]
        
        pyplot.hist(all_values, bins=20)
        pyplot.savefig(getDataPath() + "dist_gen")
        pyplot.clf()

        result = " ".join(generated)
        print (result)
        return result

    def findClosestWord(self, vector, verbose=False):
        closest_word = ""
        min_distance = -1.0
        closest_vec = []
        better_match = 0
        for word, vec in self.embeddings_index.items():
            dist = distance.euclidean(vector, vec)
            #print(vector)
            #print(vec)
            #print(word)
            if(dist < min_distance or min_distance < 0.0):
                min_distance = dist
                closest_word = word
                closest_vec = vec
                better_match += 1
                if(verbose):
                    print("--> " + closest_word + ": " + str(dist))
        
        if(verbose):
            print("Match improved %s times" %better_match)

        if(verbose):
            eucl_dist = []
            cosine_dist = []

            for word, vec in self.embeddings_index.items():
                eucl_dist.append((word, distance.euclidean(vector, vec)))
                cosine_dist.append((word, distance.cosine(vector, vec)))
            
            eucl_dist.sort(key=lambda v: v[1])
            cosine_dist.sort(key=lambda v: v[1])

            for i in range(20):
                print (str(eucl_dist[i][1]) + "  " + eucl_dist[i][0])
                print (str(cosine_dist[i][1]) + "  " + cosine_dist[i][0])
                print ("---\n")

        #print(min_distance)
        #print(vector)
        #print(closest_vec)

        return closest_word

