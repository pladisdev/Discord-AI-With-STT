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
import wave

#Outside of class so it doesn't load everytime the bot joins a discord call
#Models are: "base.en" "small.en" "medium.en" "large-v2"
audio_model = WhisperModel("medium.en", device="cuda", compute_type="int8_float16")

#Class for storing info for each speaker in discord
class Speaker():
    def __init__(self, user, data):   
        self.user = user
        
        self.data = bytes()
        self.data += data

        self.last_word = time.time()
        self.last_phrase = time.time()

        self.phrase = ""

        self.new_data = True

class WhisperSink(Sink):
    def __init__(self, queue, *, filters=None, data_length=50000, word_timeout=2, phrase_timeout=20, minimum_length=2):

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

        self.minimum_length = minimum_length

        self.running = True  

        self.temp_file = NamedTemporaryFile().name

        self.voice_queue = Queue()
        self.voice_thread = threading.Thread(target=self.insert_voice, args=())
        self.voice_thread.start()

        self.speakers = []

    #Get SST from whisper and store result into speaker
    def transcribe(self, speaker):
        #TODO Figure out the best way to save the audio fast and remove any noise
        audio_data = sr.AudioData(speaker.data, self.vc.decoder.SAMPLING_RATE, self.vc.decoder.SAMPLE_SIZE // self.vc.decoder.CHANNELS)
        wav_data = io.BytesIO(audio_data.get_wav_data())

        with open(self.temp_file, 'wb') as file:
            wave_writer = wave.open(file, 'wb')
            wave_writer.setnchannels(self.vc.decoder.CHANNELS)
            wave_writer.setsampwidth(self.vc.decoder.SAMPLE_SIZE // self.vc.decoder.CHANNELS)
            wave_writer.setframerate(self.vc.decoder.SAMPLING_RATE) 
            wave_writer.writeframes(wav_data.getvalue())
            wave_writer.close()

        #The whisper model
        segments, info = audio_model.transcribe(self.temp_file, beam_size=5)
        segments = list(segments)

        result = ""      
        for segment in segments:
            result += segment.text

        #Checks if user is saying something new
        if speaker.phrase != result:
            speaker.phrase = result
            speaker.last_word = time.time() #current_time is too delayed
    
    def insert_voice(self):

        while self.running:

            current_time = time.time()
            
            for speaker in self.speakers:
                #If the user stops saying anything new or has been speaking too long. 
                if current_time - speaker.last_word > self.word_timeout or current_time - speaker.last_phrase > self.phrase_timeout:
                    #Don't send anything if the phtase is too small
                    if len(speaker.phrase) > self.minimum_length:
                        self.queue.put_nowait({"user" : speaker.user, "result" : speaker.phrase})
                    self.speakers.remove(speaker)

            if not self.voice_queue.empty():
                
                while not self.voice_queue.empty():
                    item = self.voice_queue.get()

                    user_heard = False
                    for speaker in self.speakers:
                        if item[0] == speaker.user:
                            speaker.data += item[1]                          
                            user_heard = True
                            speaker.new_data = True
                            break

                    if not user_heard:
                        self.speakers.append(Speaker(item[0], item[1]))

                for speaker in self.speakers:
                    if speaker.new_data:
                        self.transcribe(speaker)
  
            #Loops with no wait time is bad
            time.sleep(.05)

    #Gets audio data from discord for each user talking
    @Filters.container
    def write(self, data, user):

        #Discord will send empty bytes from when the user stopped talking to when the user starts to talk again. 
        #Its only the first the first data that grows massive and its only silent audio, so its trimmed.
        data_len = len(data)
        if data_len > self.data_length:
            data = data[-self.data_length:]
        
        #Send bytes to be transcribed
        self.voice_queue.put([user, data])

    #End thread
    def close(self):
        self.running = False