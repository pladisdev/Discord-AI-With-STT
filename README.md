# Discord AI With STT
 
## Example discord bot written in python for STT, TTS, and responding to messages.
### Features
- Send messages with @ or reply to the bot and get a message back from an LLM (LLM is implemented yourself).
- Use commands to instruct the bot in different ways, with user-specific access
- Have the bot join a VC call, and listen with TTS, send the message to an LLM, and reply with TTS (TTS is implemented yourself)

## Instructions
### For STT
- Run the script.
- Enter a discord voice channel within a guild the bot has access to.
- type !join in a guild text channel.
- The bot will join and listen to what you say!

## TODO
- Provide a dummy LLM and TTS just for demonstration purpose
- The main issue is that the the Whisper sink seems to have inconsistent perfomance compared to using STT from a local audio output. I'm not sure if the audio needs to be processed before Whisper, or if there is an issue with how the bytes are saved for Whisper to transcribe.
- Whisper will return a bunch of hallucinations that come from youtube commentary that can be filtered. For example: "THANK YOU", "Make sure to like, comment, and subcribe", "you", etc.
- Use the user's role instead of hard-coding who can command the bot
- Allow the sink to collect data from multiple users talking at once, and do STT on all users talking.
