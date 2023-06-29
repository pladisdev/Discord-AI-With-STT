# Discord AI With STT
 
## Example discord bot written in python for STT, TTS, and responding to messages.

## Instructions
### For STT
- Run the script.
- Enter a discord voice channel within a guild the bot has access to.
- type !join in a guild text channel.
- The bot will join and listen to what you say!

## TODO
- The main issue is that the the Whisper sink seems to have inconsistent perfomance compared to using STT from a local audio output. I'm not sure if the audio needs to be processed before Whisper, or if there is an issue with how the bytes are saved for Whisper to transcribe.
- Whisper will return a bunch of hallucinations that come from youtube commentary that can be filtered. For example: "THANK YOU", "Make sure to like, comment, and subcribe", "you", etc.
