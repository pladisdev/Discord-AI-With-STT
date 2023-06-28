from discord.sinks.core import Filters, Sink, default_filters
import pyaudio 

#TODO Improve like the whisper_sink

class StreamSink(Sink):
    def __init__(self, device_name, *, filters=None):
        if filters is None:
            filters = default_filters
        self.filters = filters
        Filters.__init__(self, **self.filters)
        self.vc = None
        self.audio_data = {}

        self.p = pyaudio.PyAudio()
        self.device_name = device_name

        self.output_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=2,
            rate=44100,
            output=True,
            output_device_index=self.get_output_device_index()
        )

    def get_output_device_index(self):
        device_index = None
        for index in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(index)
            if info['maxOutputChannels'] > 0 and self.device_name in info['name']:
                print(self.device_name)
                device_index = index
                break
        return device_index

    @Filters.container
    def write(self, data, user): 
        data_len = len(data)
        print(data_len)
        if data_len > 8000:
            data = data[-8000:]
        self.output_stream.write(data)

    def close(self):
        self.output_stream.close()