from tempfile import NamedTemporaryFile

from bark import SAMPLE_RATE, generate_audio, preload_models
import scipy.io.wavfile as wav
import numpy as np

class TTS:
    def __init__(self):
        preload_models()
        self.sample_rate = 44100

    def tts_wav(self, text):
        audio_array = generate_audio(text)
        
        audio_array /= np.max(np.abs(audio_array))
        audio_array = (audio_array * 32767).astype(np.int16)

        temp_file = NamedTemporaryFile(delete=False).name + ".wav"
        wav.write(temp_file, self.sample_rate, audio_array)
        return temp_file