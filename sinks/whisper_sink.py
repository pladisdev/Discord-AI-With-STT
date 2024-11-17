# Default libraries
import threading
from queue import Queue
from tempfile import NamedTemporaryFile
import io
import time
import re
import wave
import asyncio

# 3rd party libraries
from discord.sinks.core import Filters, Sink, default_filters
import torch  # Had issues where removing torch causes whisper to throw an error
from faster_whisper import WhisperModel  # TODO Perhaps have option for default whisper
import speech_recognition as sr  # TODO Replace with something simpler

# Outside of class so it doesn't load everytime the bot joins a discord call
# Models are: "base.en" "small.en" "medium.en" "large-v2"
audio_model = WhisperModel("medium.en", device="cuda", compute_type="float16")

excluded_phrases = [
    "",
    "thanks",
    "tch",
    "thank you so much thank you",
    "for more information on covid-19 vaccines visit our website",
    "thank you very much",
    "thank you very much.",
    "we'll be right back.",
    "subs by www.zeoranger.co.uk",
    "hello everyone",
    "thank you bye",
    "thank you",
    "all right",
    "thank you thank you",
    "thank you for watching",
    "thanks for watching",
    "i'll see you next time",
    "got to cancel",
    "shh",
    "wow",
    "shhh",
    "hello",
    "you",
    "the",
    "yeah",
    "but",
    "heh heh",
    "heh",
    "bye",
    "okay",
    "silence",
]


# Class for storing info for each speaker in discord
class Speaker:
    def __init__(self, user, data):
        self.user = user

        self.data = [data]

        self.start_time = time.time()
        self.last_word = self.start_time

        self.word_timeout = 0

        self.phrase = ""

        self.empty_bytes_counter = 0
        self.new_bytes = 1


class WhisperSink(Sink):
    """A sink for discord that takes audio in a voice channel and transcribes it for each user.\n

    Uses faster whisper for transcription. can be swapped out for other audio transcription libraries pretty easily.\n

    Inputs:\n
    queue - Used for sending the transcription output to a callback function\n
    filters - Some discord thing I'm not sure about\n
    data_length - The amount of data to save when user is silent but their mic is still active\n
    quiet_phrase_timeout - A larger timeout for when the transcription has detected the user is in mid sentence\n
    mid_sentence_multiplier - A smaller timout when the transcription has detected the user has finished a sentence\n
    no_data_multiplier - If the user has stopped talking on discord completely (Their icon is no longer green), reduce both timeouts by a percantage to improve inference time\n
    max_phrase_timeout - Send out the current transcription after x seconds if the user continues to talk for a long period\n
    min_phrase_length - Minimum length of transcription to reduce noise\n
    max_speakers - The amount of users to transcribe when all speakers are talking at once.\n
    """

    class SinkSettings:
        def __init__(self,                   
                    data_length=50000,
                    quiet_phrase_timeout=1.2,
                    mid_sentence_multiplier=1.8,
                    no_data_multiplier=0.75,
                    max_phrase_timeout=30,
                    min_phrase_length=3,
                    max_speakers=-1
                    ):          

            self.data_length = data_length
            self.quiet_phrase_timeout = quiet_phrase_timeout
            self.mid_sentence_multiplier = mid_sentence_multiplier
            self.no_data_multiplier = no_data_multiplier
            self.max_phrase_timeout = max_phrase_timeout
            self.min_phrase_length = min_phrase_length
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
        self.audio_data = {}

        self.running = True

        self.speakers = []

        self.temp_file = NamedTemporaryFile().name

        self.voice_queue = Queue()
        self.voice_thread = threading.Thread(target=self.insert_voice, args=())
        self.voice_thread.start()

    def is_valid_phrase(self, speaker_phrase, result):
        cleaned_result = re.sub(r"[.!?,]", "", result).lower().strip()
        return speaker_phrase != result and cleaned_result not in excluded_phrases

    def transcribe_audio(self, temp_file):
        # The whisper model
        start_time = time.time()
        segments, info = audio_model.transcribe(
            temp_file,
            beam_size=10,
            best_of=3,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=250 ),
            no_speech_threshold = 0.6,

        )
        segments = list(segments)
        result = ""
        for segment in segments:
            result += segment.text
        print(f"Transcribe: {time.time() - start_time}")
        print(result)
        return result

    # Get SST from whisper and store result into speaker
    def transcribe(self, speaker: Speaker):
        # TODO Figure out the best way to save the audio fast and remove any noise
        audio_data = sr.AudioData(
            bytes().join(speaker.data),
            self.vc.decoder.SAMPLING_RATE,
            self.vc.decoder.SAMPLE_SIZE // self.vc.decoder.CHANNELS,
        )
        wav_data = io.BytesIO(audio_data.get_wav_data())

        with open(self.temp_file, "wb") as file:
            wave_writer = wave.open(file, "wb")
            wave_writer.setnchannels(self.vc.decoder.CHANNELS)
            wave_writer.setsampwidth(
                self.vc.decoder.SAMPLE_SIZE // self.vc.decoder.CHANNELS
            )
            wave_writer.setframerate(self.vc.decoder.SAMPLING_RATE)
            wave_writer.writeframes(wav_data.getvalue())
            wave_writer.close()

        # Transcribe results takes wav file (self.temp_file) and outputs transcription
        transcription = self.transcribe_audio(self.temp_file)

        # Checks if user is saying a new valid phrase
        if self.is_valid_phrase(speaker.phrase, transcription):
            speaker.empty_bytes_counter = 0

            speaker.word_timeout = self.sink_settings.quiet_phrase_timeout

            # Detect if user is mid sentence and delay sending full message
            if re.search(r"\s*\.{2,}$", transcription) or not re.search(
                r"[.!?]$", transcription
            ):
                speaker.word_timeout = (
                    speaker.word_timeout * self.sink_settings.mid_sentence_multiplier
                )

            speaker.phrase = transcription
            speaker.last_word = time.time()

        # If user's mic is on but not saying anything, remove those bytes for faster inference.
        elif speaker.empty_bytes_counter > 5:
            speaker.data = speaker.data[: -speaker.new_bytes]
        else:
            speaker.empty_bytes_counter += 1

    def insert_voice(self):
        while self.running:
            if not self.voice_queue.empty():
                # Sorts data from queue for each speaker after each transcription
                while not self.voice_queue.empty():
                    item = self.voice_queue.get()

                    user_heard = False
                    for speaker in self.speakers:
                        if item[0] == speaker.user:
                            speaker.data.append(item[1])
                            user_heard = True
                            speaker.new_bytes += 1
                            break

                    if not user_heard:
                        if (
                            self.sink_settings.max_speakers < 0
                            or len(self.speakers) <= self.sink_settings.max_speakers
                        ):
                            self.speakers.append(Speaker(item[0], item[1]))

            # STT for each speaker currently talking on discord
            for speaker in self.speakers:
                # No reason to transcribe if no new data has come from discord.
                if speaker.new_bytes > 0:
                    self.transcribe(speaker)
                    speaker.new_bytes = 0
                    word_timeout = speaker.word_timeout
                else:
                    # No data coming in from discord, reduces word_timeout for faster inference
                    word_timeout = speaker.word_timeout * self.sink_settings.no_data_multiplier

                current_time = time.time()

                if len(speaker.phrase) >= self.sink_settings.min_phrase_length:
                    # If the user stops saying anything new or has been speaking too long.
                    part1 = current_time - speaker.last_word > word_timeout
                    part2 = current_time - speaker.start_time > self.sink_settings.max_phrase_timeout
                    if (part1 or part2):
                        print(f"Stop talking: {part1}. Too long: {part2}")
                        self.loop.call_soon_threadsafe(self.queue.put_nowait, {"user": speaker.user, "result": speaker.phrase})

                        self.speakers.remove(speaker)
                elif current_time > self.sink_settings.quiet_phrase_timeout * 2:
                    # Reset Remove the speaker if no valid phrase detected after set period of time
                    self.speakers.remove(speaker)

            # Loops with no wait time is bad
            time.sleep(0.45)

    # Gets audio data from discord for each user talking
    @Filters.container
    def write(self, data, user):
        # Discord will send empty bytes from when the user stopped talking to when the user starts to talk again.
        # Its only the first the first data that grows massive and its only silent audio, so its trimmed.

        data_len = len(data)
        if data_len > self.sink_settings.data_length:
            data = data[-self.sink_settings.data_length :]

        # Send bytes to be transcribed
        self.voice_queue.put([user, data])

    # End thread
    def close(self):
        self.running = False
        self.queue.put_nowait(None)
