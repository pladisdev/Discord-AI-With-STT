#Default libraries
import threading
from queue import Queue
from tempfile import NamedTemporaryFile
import io
import time

#3rd party libraries
from discord.sinks.core import Filters, Sink, default_filters
import torch #Had issues where removing torch causes whisper to throw an error
from faster_whisper import WhisperModel #TODO Perhaps have option for default whisper
import speech_recognition as sr #TODO Replace with something simpler

#Outside of class so it doesn't load everytime the bot joins a discord call
#Models are: "base.en" "small.en" "medium.en" "large-v2"
audio_model = WhisperModel("large-v2", device="cuda", compute_type="int8_float16")

class WhisperSink(Sink):
    def __init__(self, queue, *, filters=None, data_length=50000, word_timeout=2, phrase_timeout=20):

        self.queue = queue

        if filters is None:
            filters = default_filters
        self.filters = filters
        Filters.__init__(self, **self.filters)
   
        self.vc = None
        self.audio_data = {}

        self.data_length = data_length
        self.word_timeout = word_timeout
        self.phrase_timeout = phrase_timeout

        self.last_word = 0
        self.last_phrase = 0

        self.running = True  

        self.current_user = None   

        self.temp_file = NamedTemporaryFile().name

        self.last_sample = bytes()

        self.result = ""

        self.transcribe_queue = Queue()
        self.phrase_end = threading.Thread(target=self.transcribe, args=())
        self.phrase_end.start()

    def transcribe(self):

        while self.running:
            if  self.current_user is None:
                self.last_word = time.time()
                self.last_phrase = time.time()
            else:
                current_time = time.time()
                #If the user stops saying anything new or has been speaking too long. 
                if len(self.result) > 2 and (current_time - self.last_word > self.word_timeout or current_time - self.last_phrase > self.phrase_timeout):
                    self.last_sample = bytes()
                    self.current_user = None
                    self.queue.put_nowait(self.result)
                    self.result = ""
                    self.last_phrase = current_time

                #When data from discord is available 
                if not self.transcribe_queue.empty():

                    while not self.transcribe_queue.empty():
                        self.last_sample += self.transcribe_queue.get()

                    audio_data = sr.AudioData(self.last_sample, self.vc.decoder.SAMPLING_RATE, self.vc.decoder.SAMPLE_SIZE // self.vc.decoder.CHANNELS)
                    wav_data = io.BytesIO(audio_data.get_wav_data())

                    with open(self.temp_file, 'w+b') as f:
                        f.write(wav_data.read())

                    #The whisper model
                    segments, info = audio_model.transcribe(self.temp_file, beam_size=5)
                    segments = list(segments)

                    result = ""      
                    for segment in segments:
                        result += segment.text

                    #Checks if user is saying something new
                    if self.result != result:
                        self.result = result
                        self.last_word = time.time() #current_time is too delayed
            
            #Loops with no wait time is bad
            time.sleep(.01)

    #Gets audio data from discord for each user talking
    @Filters.container
    def write(self, data, user):

        if self.current_user is None:
            self.current_user = user 
        
        #The first user that starts talking is selected, other users are ignored until the first user stops speaking
        if self.current_user == user:
            
            #Discord will send empty bytes from when the user stopped talking to when the user starts to talk again. 
            #Its only the first the first data that grows massive and its only silent audio, so its trimmed.
            data_len = len(data)
            if data_len > self.data_length:
                data = data[-self.data_length:]
            
            #Send bytes to be transcribed
            self.transcribe_queue.put(data)

    #End thread
    def close(self):
        self.running = False