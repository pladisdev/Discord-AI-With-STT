#Default libraries
import asyncio
from asyncio import Queue
from enum import Enum
import time

#3rd party libraries
from discord.sinks.core import Filters, Sink, default_filters
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

class Speaker():
    class SpeakerState(Enum):
        RUNNING = 1
        TRANSCRIBE = 2
        FINALIZE = 3
        STOP = 4

    def __init__(self, loop : asyncio.BaseEventLoop, out_queue : Queue, deepgram_API_key, sentence_end=300, utterance_end=1000):   
        self.loop = loop
        self.queue = out_queue

        self.deepgram_API_key = deepgram_API_key

        self.sentence_end = sentence_end
        self.utterance_end = utterance_end
        
        self.user = None
        self.data = []

        self.new_bytes = False
        self.last_byte = 0       

        self.silent_packet = b"\x00" * 320

        self.state = self.SpeakerState.RUNNING    
        
    def add_user(self, user):
        self.user = user
        self.loop.create_task(self.deep_stream())

    def add_data(self, data, current_time):
        self.data.append(data)
        self.new_bytes = True
        self.last_byte = current_time

    def add_silence(self):
        self.data.append(self.silent_packet)

    def reset_data(self):
        self.data = []
        self.new_bytes = False

    async def deep_stream(self):
        global is_finals
        global queue
        global user

        user = self.user
        queue = self.queue
        is_finals = []

        try:
            config: DeepgramClientOptions = DeepgramClientOptions(
                options={"keepalive": "true"},
            )
            deepgram: DeepgramClient = DeepgramClient(self.deepgram_API_key, config)
            dg_connection = deepgram.listen.asyncwebsocket.v("1")

            async def on_open(self, open, **kwargs):
                print("Connection Open")

            async def on_message(self, result, **kwargs):
                global is_finals
                global queue
                sentence = result.channel.alternatives[0].transcript
                if len(sentence) == 0:
                    return
                if result.is_final:
                    is_finals.append(sentence)
                    if result.speech_final:
                        utterance = " ".join(is_finals)
                        print(f"Speech Final: {utterance}")                      
                    else:
                        print(f"Is Final: {sentence}")
                else:
                    print(f"Interim Results: {sentence}")

            async def on_metadata(self, metadata, **kwargs):
                print(f"Metadata: {metadata}")

            async def on_speech_started(self, speech_started, **kwargs):
                print("Speech Started")
                
            async def on_utterance_end(self, utterance_end, **kwargs):               
                global is_finals
                global queue
                global user

                print("Utterance End")

                if len(is_finals) > 0:
                    utterance = " ".join(is_finals)
                    print(f"Utterance End: {utterance}")
                    await queue.put({"user" : user, "result" : utterance})
                    is_finals = []

            async def on_close(self, close, **kwargs):
                print("Connection Closed")

            async def on_error(self, error, **kwargs):
                print(f"Handled Error: {error}")

            async def on_unhandled(self, unhandled, **kwargs):
                print(f"Unhandled Websocket Message: {unhandled}")

            dg_connection.on(LiveTranscriptionEvents.Open, on_open)
            dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
            dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
            dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
            dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
            dg_connection.on(LiveTranscriptionEvents.Close, on_close)
            dg_connection.on(LiveTranscriptionEvents.Error, on_error)
            dg_connection.on(LiveTranscriptionEvents.Unhandled, on_unhandled)

            # connect to websocket
            options: LiveOptions = LiveOptions(
                model="nova-2",
                language="en-US",
                smart_format=True,
                encoding="linear16",
                channels=2,
                sample_rate=48000,
                interim_results=True,
                utterance_end_ms=f"{self.utterance_end}", #cannot be less than 1000ms
                vad_events=True,
                endpointing=self.sentence_end,
            )

            addons = {
                "no_delay": "true"
            }

            if await dg_connection.start(options, addons=addons) is False:
                print("Failed to connect to Deepgram")
                return

            while self.state != self.SpeakerState.STOP:
                if self.state == self.SpeakerState.TRANSCRIBE:
                    await dg_connection.send(b"".join(self.data))
                    self.reset_data()
                    self.state = self.SpeakerState.RUNNING
                    
                elif self.state == self.SpeakerState.FINALIZE:
                    await dg_connection.finalize()
                    self.reset_data()
                    self.state = self.SpeakerState.RUNNING
                else:
                    await asyncio.sleep(.005)

            await dg_connection.finish()
            await asyncio.sleep(1)

        except Exception as e:
            print(f"Could not open socket: {e}")
            return

class DeepgramSink(Sink):

    class SinkSettings:
        def __init__(self, deepgram_API_key,sentence_end = 300,utterence_end = 1000, data_length=25000, max_speakers=-1):   
            self.deepgram_API_key = deepgram_API_key
            self.sentence_end = sentence_end
            self.utterence_end = utterence_end
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
                                                         self.sink_settings.deepgram_API_key, 
                                                         self.sink_settings.sentence_end, 
                                                         self.sink_settings.utterence_end))
                            self.speakers[-1].add_user(item[0])
                            self.speakers[-1].add_data(item[1], current_time)
            else:  
                #Loops with no wait time is bad
                await asyncio.sleep(.02)

            for speaker in self.speakers:
                #Transcribe when new data is available
                if speaker.new_bytes:
                    speaker.state = speaker.SpeakerState.TRANSCRIBE
                #finalize data if X seconds passes from last data packet from discord
                elif current_time > speaker.last_byte + speaker.utterance_end/1000:
                    speaker.state = speaker.SpeakerState.FINALIZE   
                #add silence to help process utterance
                elif  current_time > speaker.last_byte + speaker.sentence_end/1000:
                    speaker.add_silence()
        
        for speaker in self.speakers:     
            speaker.state = speaker.SpeakerState.STOP

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