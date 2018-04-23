"""Script to generate new tweets from a given tweet history.

For details on tweet input, refer to tweet_helper.py

This script will generate new output folder, with a unique name,
specifying network settings and timestamp.
The output folder will contain the following:
- loss funciton history log file (history.log)
- loss history chart (chart.png)
- latest saved model configuration (model.h5)
- error log file (error.log)
- multiple files containing new tweets, 
  generated by LSTM, after each epoch (zepoch_x.txt)

The output will be updated after each epoch, 
allowing to monitor network's training progress.

In case if training was interrupted prematurely, 
it can be continued by adding "resume" parameter to a script launching command.
It will locate output folder of the network with specified network config
and latest timestamp, load last saved model, and continue the training.
"""

import sys
import io
import traceback
import random
import datetime

import numpy as np

import tensorflow as tf
config = tf.ConfigProto()
config.gpu_options.allow_growth = True
session = tf.Session(config=config)

from keras.layers import LSTM, Dense, Activation, Dropout, CuDNNLSTM
from keras.models import Sequential
from keras.optimizers import RMSprop, Adam
from keras.callbacks import LambdaCallback, ModelCheckpoint, CSVLogger
from keras.models import load_model
from keras.regularizers import l1, l2, l1_l2

from filesystem_helper import getDataPath, getModelPath, getLastTimestamp
from history_helper import plotHistory, getEpochsElapsed
from tweets_helper import getTweets, shuffledTweets
from char_sequence_helper import CharSequenceProvider
from word_sequence_helper import WordSequenceProvider
from weights_helper import saveWeights

def on_epoch_end(epoch, logs):
    """Callback function that is being executed at the eng of each training epoch.

    It completes 3 actions:
    - updates train/validation loss function value history;
    - generates new tweets using state of the model after previous epoch;
    - shuffles input tweets.
    (last 2 can be disabled by setting generate_on_epoch and shuffle_on_epoch triggers to False)

    Caution! In addition to epoch and logs parameters, it relies on multiple global variables. 
    Such design is used due to callback function interface in keras.
    """

    plotHistory(model_name, timestamp)

    saveWeights(model, model_name, timestamp, epoch)

    if(generate_on_epoch):
        text_file = open(getModelPath(model_name, timestamp) + "zepoch_" + str(epoch) + ".txt", 'w')
        latest_generated = open(getDataPath() + "latest_tweets.txt", 'w')
        
        for temperature in [1.0]:
            temperature_notice = '\n----- temperature:' + str(temperature) + "\n"
            text_file.write(temperature_notice)
            latest_generated.write(temperature_notice)
            
            generated = sequence_provider.generateText(model, seed_sentence, generated_text_size, maxlen, temperature)
            
            text_file.write(generated)
            latest_generated.write(generated)
        
        text_file.close()
        latest_generated.close()

    if(shuffle_on_epoch):
        shuffled_tweets = shuffledTweets(train_tweets)
        x, y = sequence_provider.getSequences(shuffled_tweets, maxlen)
        np.copyto(train_x, x)
        np.copyto(train_y, y)

# Uncomment this for experiment reproducibility.
random.seed(42)

#sequence_provider = CharSequenceProvider()
sequence_provider = WordSequenceProvider()

# Neural network layers config.
num_layers = 1
num_neurons = 64
dropout = 0.0
input_dropout = 0.0
recurrent_dropout = 0.0

# Training config.
batch_size = 1000
learning_rate = 0.002
data_fraction = 1
maxlen = 5
data_augmentation = 3

penalty = l2(0.00001)
penalty_str = 'l2(0,00001)'

shuffle_on_epoch = False
total_epochs = 30
# Text generation config.
generate_on_epoch = False
generated_text_size = 20
seed_sentence = 'Our thoughts and prayers go out to the families and loved ones of the brave troops lost in the helicopter crash on the Iraq-Syria border yesterday.'

model_name = str(num_layers) + "x" + str(num_neurons)
model_name += "-" + str(dropout).replace('.', ',')
model_name += "-" + str(batch_size)
model_name += "-" + str(learning_rate).replace('.', ',')
model_name += "-" + str(data_fraction)
model_name += "-" + str(maxlen)
model_name += "-x" + str(data_augmentation)
#model_name += "-" + str(input_dropout)
#model_name += "-" + str(recurrent_dropout)

t = datetime.datetime.now()
timestamp = t.strftime("%y_%m_%d-%H_%M")

# Use "resume" as a command line argument to continue interrupted training.
resuming = False
if(len(sys.argv) > 1 and sys.argv[1] == "resume"):
    resuming = True
    timestamp = getLastTimestamp(model_name)
    print("resuming: " + model_name + " " + timestamp)

try:
    # Loading tweets corpus from files.
    train_tweets, test_tweets = getTweets(data_fraction, data_augmentation)

    full_text = train_tweets + test_tweets + seed_sentence
    sequence_provider.initialize(full_text)
    
    # Generating char sequences of maxlen length.
    train_x, train_y = sequence_provider.getSequences(train_tweets, maxlen)
    test_x, test_y = sequence_provider.getSequences(test_tweets, maxlen)
    
    print('Building model...')
    model = Sequential()
    
    # Adding LSTM layers.
    #
    # Setting return_sequences=True is necessary for the layers that feed their output
    # to another LSTM layer (which accepts char sequences).
    # 
    # Setting dropout for all LSTM layers, except the first one, because it is applied to layer input.
    #
    if(num_layers > 1):
        model.add(LSTM(num_neurons, return_sequences=True, input_shape=train_x.shape[1:]))
        for i in range(num_layers - 2):
            model.add(LSTM(num_neurons, return_sequences=True, dropout=dropout))
        model.add(LSTM(num_neurons, dropout=dropout))
    else:
        model.add(CuDNNLSTM(num_neurons, input_shape=train_x.shape[1:]))
    
    if(dropout > 0.0):
        model.add(Dropout(dropout))


    # Output layer.
    model.add(Dense(train_y.shape[1]))
    #model.add(Activation('tanh'))

    optimizer = Adam(lr=learning_rate)
    
    model.compile(loss='mean_squared_error', optimizer=optimizer)

    epochs_elapsed = 0

    model_path = getModelPath(model_name, timestamp) + 'model.h5'

    if(resuming):
        # If resuming training, last saved model is loaded, along with the number of epochs it has been trained for.
        model = load_model(model_path)
        epochs_elapsed = getEpochsElapsed(model_name, timestamp)
        print("epochs elapsed: " + str(epochs_elapsed))

    # Callbacks:
    # - Saving train/validation loss function values to a file. 
    csv_logger = CSVLogger(getModelPath(model_name, timestamp) + 'history.log', append = resuming)
    # - Custom lambda callback (See function on_epoch_end() declaration for more details).
    print_callback = LambdaCallback(on_epoch_end=on_epoch_end)
    # - Saving model weights and optimizer state after each epoch.
    checkpointer = ModelCheckpoint(filepath = model_path, verbose=1, save_best_only=False)

    history = model.fit(train_x, train_y,
        batch_size = batch_size,
        epochs = total_epochs-epochs_elapsed,
        callbacks = [csv_logger, print_callback, checkpointer],
        validation_data = (test_x, test_y))
except:
    # Saving error log for debugging.
    error_log_file = open(getModelPath(model_name, timestamp) + "error.log", "w")
    traceback.print_exc(file=error_log_file)
    error_log_file.close()
    
    raise