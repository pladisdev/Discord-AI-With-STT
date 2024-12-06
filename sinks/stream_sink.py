#Default libraries
import asyncio
from asyncio import Queue
import time

#3rd party libraries
from discord.sinks.core import Filters, Sink, default_filters
from sinks.whisper_stream.whisper_online import *

asr = FasterWhisperASR("en", "medium.en")  # loads and wraps Whisper model
asr.use_vad()

DISCORD_SAMPLING = 48000
WHISPER_SAMPLING = 16000

class Speaker():
    def __init__(self, loop : asyncio.BaseEventLoop, out_queue : Queue, min_chunk=1000):   
        self.loop = loop
        self.queue = out_queue

        #minimum value in seconds to process audio buffer
        self.min_chunk = min_chunk/1000
        
        self.user = None
        self.data = []

        self.last_byte = 0

        self.phrases = []

        self.online = OnlineASRProcessor(asr)
        self.online.init()

        self.in_processing = False
        self.is_first = True

        self.running = True
               
    def add_user(self, user):
        self.user = user
        asyncio.create_task(self.stream())

    def add_data(self, data, current_time):
        self.data.append(data)
        self.last_byte = current_time

    def add_silence(self):
        sample_rate = DISCORD_SAMPLING
        channels = 2
        bit_depth = 16

        bytes_per_sample = bit_depth // 8
        total_samples = int(sample_rate * channels * (self.min_chunk*5))
        total_bytes = total_samples * bytes_per_sample

        silent_packet = b'\x00' * total_bytes

        self.data.append(silent_packet)

    #TODO remake this godsforsaken conversion, has some noise from conversion
    def convert_audio(self, audio_bytes):
        #a = np.frombuffer(audio_bytes, np.int16).flatten().astype(np.float32)/32768.0
        s_f = sf.SoundFile(io.BytesIO(audio_bytes), channels=2,endian="LITTLE",samplerate=DISCORD_SAMPLING, subtype="PCM_16",format="RAW")
        a, _ = librosa.load(s_f,sr=WHISPER_SAMPLING, mono=True,dtype=np.float32)  
        return a

    async def recieve_audio_chunk(self):
        if len(self.data) == 0:
            return None

        minlimit = self.min_chunk*DISCORD_SAMPLING
        out = []

        a = self.convert_audio(b"".join(self.data))
        
        assert a.dtype == np.float32, "Audio data should be float32."
        assert -1.0 <= a.min() and a.max() <= 1.0, "Audio data should be normalized between -1.0 and 1.0."
        assert len(a) > 0, "Audio data should not be empty."
        out.append(a)
        
        if sum(len(x) for x in out) < minlimit:
            return None
        
        self.data = []
        
        if not out:
            return None
        conc = np.concatenate(out)
        if self.is_first and len(conc) < minlimit:
            return None
        self.is_first = False
        return np.concatenate(out)

    async def stream(self):
        while self.running:
            a = await self.recieve_audio_chunk()
            if a is not None:
                await self.transcript_check(a)
                self.in_processing = True

            await asyncio.sleep(.001)

    def end(self):
        self.running = False

    async def transcript_check(self, a):     
            self.online.insert_audio_chunk(a)
            self.data = []
            try:
                loop = asyncio.get_event_loop()
                transcript = await loop.run_in_executor(None, self.online.process_iter,)
            except AssertionError as e:
                logger.error(f"assertion error: {e}")
                pass
            else:
                if transcript[0] is not None:
                    #TODO Logic for using VAD for processing
                    self.phrases.append(transcript[2]) 

    async def send_transcript(self, transcript):
        self.online.init()
        self.in_processing = False
        self.phrases = []
        await self.queue.put({"user" : self.user, "result" : transcript})
        
    async def finish_transcript(self):
        self.add_silence()
        while True:
            a = await self.recieve_audio_chunk()
            if a is None:
                break
            await self.transcript_check(a)
        
        transcript = self.online.finish() 
        
        if transcript[0] is not None:
            self.phrases.append(transcript[2])
        await self.send_transcript("".join(self.phrases))

class StreamSink(Sink):

    class SinkSettings:
        def __init__(self, min_chunk = 1000, data_length=25000, max_speakers=-1):   
            self.min_chunk = min_chunk
            self.data_length = data_length
            self.max_speakers = max_speakers

    def __init__(self, *, filters=None, sink_settings : SinkSettings, queue : asyncio.Queue, loop : asyncio.AbstractEventLoop):
        if filters is None:
            filters = default_filters
        self.filters = filters
        Filters.__init__(self, **self.filters)
        
        self.sink_settings = sink_settings
        self.queue = queue
        self.loop = loop
   
        self.vc = None

        self.running = True  

        self.voice_queue = Queue()
        self.speakers = []
        self.loop.create_task(self.insert_voice()) 

    async def insert_voice(self):

        while self.running:
            
            current_time = time.time()
            if not self.voice_queue.empty():  
                #Sorts data from queue for each speaker after each transcription             
                while not self.voice_queue.empty():                  
                    item = await self.voice_queue.get()

                    user_exists = False
                    for speaker in self.speakers:     
                        if speaker.user is None:
                            speaker.add_user(item[0])
                                       
                        if item[0] == speaker.user:
                            speaker.add_data(item[1], current_time)                          
                            user_exists = True
                            break

                    if not user_exists:
                        #add new user to speakers
                        if self.sink_settings.max_speakers < 0 or len(self.speakers) <= self.sink_settings.max_speakers:
                            self.speakers.append(Speaker(self.loop, 
                                                         self.queue,
                                                         self.sink_settings.min_chunk))
                            self.speakers[-1].add_user(item[0])
                            self.speakers[-1].add_data(item[1], current_time)
            else:  
                #Loops with no wait time is bad
                await asyncio.sleep(.02)

            for speaker in self.speakers:
                #finalize data if X seconds passes from last data packet from discord
                if current_time > speaker.last_byte + speaker.min_chunk and speaker.in_processing:
                    await speaker.finish_transcript()

        for speaker in self.speakers:
            speaker.end()

    #Gets audio data from discord for each user talking
    @Filters.container
    def write(self, data, user):
        data_len = len(data)
        if data_len > self.sink_settings.data_length:
            data = data[-self.sink_settings.data_length+int(self.sink_settings.data_length/10):]
        
        #Send bytes to be transcribed
        self.voice_queue.put_nowait([user, data])

    #End thread
    def close(self):
        self.running = False
        self.queue.put_nowait(None)
