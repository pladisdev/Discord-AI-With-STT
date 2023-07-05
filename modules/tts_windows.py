import pyttsx3
from tempfile import NamedTemporaryFile

class TTS:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 250)
        voices = self.engine.getProperty('voices')
        self.engine.setProperty('voice', voices[0].id)  # Select the first voice from available voices
        self.sample_rate = 44100

    def tts_wav(self, text):
        temp_file = NamedTemporaryFile().name + ".wav"
        self.engine.save_to_file(text, temp_file)
        self.engine.runAndWait()
        return temp_file