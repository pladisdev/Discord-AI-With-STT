# Discord AI With STT

## Notice
This is designed to be repurposed for individual projects. This is not a plug-and-play discord bot. The main purpose is to demonstrate how discord sinks can be used with STT, LLMs, and TTS. 
## Updates
- Added deepgram sink, which allows audio streaming for STT. Improves latency massively espicially for long sequences of dialogue. Can be repurposed for local STT streaming and other services.
- Reduced latency for getting discord name from user id by doing the search only once.
- Improved settings for each sink with some standardization.
- stream_sink obselete till further work is done.

## Example discord bot written in python for STT, TTS, and responding to messages.
### Features
- Send messages with @ or reply to the bot and get a message back from an LLM
- Use commands to instruct the bot in different ways, with user-specific access
- Have the bot join a VC call, and listen with STT (and know the name of the user talking), send the message to an LLM, and reply with TTS
- Able to understand multiple user's talking at once, and output each transcription with username

## Instructions
### Installation - Tested on Windows
- You will need FFMPEG installed for the bot to speak in discord. ```https://ffmpeg.org/```
- Seems like you need python >= 3.8 and <= 3.10. try removing the version requirements in the pip install for older python versions.
- You'll need to install torch for your PC. I tested with cuda 11.8. ```https://pytorch.org/get-started/locally/```
- ```pip install -r requirements.txt``` for the required libraries after installing torch. (Note: I previously assumed you needed discord.py instead of py-cord. But it may be you need both)
- Create a discord bot using the Discord Developer Portal and add the bot the server you want the bot in. Permissions (I believe) needed are Read Messages, Speak, Connect. ```https://discord.com/developers```
- Add the token to your environmental variables. Example for windows: ```setx DISCORD_TOKEN <your-token-here>``` on powershell with admin
- Edit the discord_AI script with which roles and persons you want to be able to command the bot.

### Deepgram Sink
- You will need to create a deepgram account and get an API Key
- Add the API key to DEEPGRAM_API_KEY
- You will get a lot of hours of free credits so no need for payment

### Bot command permissions
 - In the code you can specify which roles and users can use the bot commands
 - COMMAND_ROLES requires a lower case name of the role in your guild
 - COMMAND_USERS requires your User ID. Right click a user's name to get their ID in discord.
 - Leaving both empty allows anyone to command the bot.
 - REPLY_CHANNELS decides which channel ID in your guild the bot can reply to user in. Keep empty to allow all channels. Right channels in your discord to get the ID.


### Commands
- ```!join``` to have the bot join a VC you are currently in
- ```!leave``` to have the bot leave your VC
- ```!quit``` to close the program

### Messaging in guild
- Just @ or reply to your bot to get a response
  
### For STT
- Enter a discord voice channel within a guild the bot has access to.
- type ```!join``` in a guild text channel.
- The bot will join and listen to what you say!
- The bot will respond after taking a few seconds to process what you said when you stop talking

## TODO
- With the deepgram sink, the same framework can be applied for Whisper Streaming ```https://github.com/ufal/whisper_streaming```. However work needs to be done to detect utterenance and get the audio in the correct format.
- Provide better logic to handle if user is no longer speaking, espicially in a large group.
- A lot more

## Issues
- Whisper will return a bunch of hallucinations that come from youtube commentary that can be filtered. For example: "THANK YOU", "Make sure to like, comment, and subcribe", "you", etc.
- Possibility for a speaker to be cut off early when a large group is talking due to whisper processing taking too long

## Example
Modified code used for the AI vtuber Aiko.
https://youtu.be/8Giv5mupJNE?si=McmVyD9Qf12-8YY4
