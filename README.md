# Discord AI With STT
 
## Example discord bot written in python for STT, TTS, and responding to messages.
### Features
- Send messages with @ or reply to the bot and get a message back from an LLM (LLM is implemented yourself).
- Use commands to instruct the bot in different ways, with user-specific access
- Have the bot join a VC call, and listen with STT (and know the name of the user talking), send the message to an LLM, and reply with TTS (TTS is implemented yourself)
- Able to understand multiple user's talking at once, and output each transcription with username

## Instructions
### Installation - Tested on Windows
- You will need FFMPEG installed for the bot to speak in discord. ```https://ffmpeg.org/```
- Seems like you need python >= 3.8. try removing the version requirements in the pip install for older python versions.
- You'll need to install torch for your PC. I tested with cuda 11.8. ```https://pytorch.org/get-started/locally/```
- ```pip install -r requirements.txt``` for the required libraries after installing torch.
- Create a discord bot using the Discord Developer Portal and add the bot the server you want the bot in. Permissions (I believe are) needed are Read Messages, Speak, Connect. ```https://discord.com/developers```
- Edit the discord_AI script with your discord bot TOKEN and edit which roles and persons you want to be able to command the bot.
  
### For STT
- Run the script.
- Enter a discord voice channel within a guild the bot has access to.
- type !join in a guild text channel.
- The bot will join and listen to what you say!

## TODO
- Provide a dummy LLM and TTS just for demonstration purpose
- Provide better logic to handle if user is no longer speaking, espicially in a large group.
- A lot more

## Issues
- Whisper will return a bunch of hallucinations that come from youtube commentary that can be filtered. For example: "THANK YOU", "Make sure to like, comment, and subcribe", "you", etc.
- Possibility for a speaker to be cut off early when a large group is talking
