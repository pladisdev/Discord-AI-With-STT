import asyncio

import discord
from discord.ext import commands
from discord import FFmpegOpusAudio

#You should replace these with your llm and tts of choice
#llm_dialo for fast but awful conversation
#llm_guan_3b for slow but better conversation
from modules import llm_guan_3b as llm, tts_windows as tts

from os import environ
from sys import exit
TOKEN = environ.get("DISCORD_TOKEN", None) 
if TOKEN is None:
    print("Need to set DISCORD_TOKEN in environmental variables. Exiting program.")
    exit()

#DEEPGRAM_API_KEY = environ.get("DEEPGRAM_API_KEY", None)
#from sinks.deepgram_sink import DeepgramSink as Sink #Connects to deepgram, requires API key
#sink_settings = Sink.SinkSettings(DEEPGRAM_API_KEY, 300, 1000, 25000, 2)

#from sinks.whisper_sink import WhisperSink as Sink #User whisper to transcribe audio and outputs to TTS
#sink_settings = Sink.SinkSettings(50000, 1.2, 1.8, 0.75, 30, 3, -1)

from sinks.stream_sink import StreamSink  as Sink
sink_settings = Sink.SinkSettings(500, 25000, 2)

#This is who you allow to use commands with the bot, either by role, user or both.
#can be a list, both being empty means anyone can command the bot. Roles should be lowercase, USERS requires user IDs
COMMAND_ROLES = []
COMMANDS_USERS = []

#Enter the channel IDs for which channels you want the bot to reply to users. Keep empty to allow all channels.
REPLY_CHANNELS = []

loop = asyncio.get_event_loop()
intents = discord.Intents.all()
client = commands.Bot(command_prefix="!", intents=intents, loop=loop)

ai = llm.LLM()
speech = tts.TTS()
  
voice_channel = None

class DiscordUser:
    def __init__(self):
        self.user_id = None
        self.username = None

    async def add_user(self, user_id):
        self.user_id = user_id
        self.username = await get_username(user_id)  
        return self.username
        
#In a seperate async thread, recieves messages from STT
async def whisper_message(queue : asyncio.Queue):
 
 #store user names based on their id
 discord_users = []

 while True:
    response = await queue.get()

    if response is None:
        break
    else:
        user_id = response["user"]
        text = response["result"]

        #Check if user name already exists to reduce time calling get_username
        user_exists= False
        username = None
        for discord_user in discord_users:
            if discord_user.user_id == user_id:
                username = discord_user.username
                user_exists = True
                break    
        if not user_exists:
            discord_users.append(DiscordUser())
            username = await discord_users[-1].add_user(user_id)

        print(f"Detected Message: {text}")
        
        if username is not None:
            answer = await loop.run_in_executor(None, ai.chat, username, text)
            await play_audio(answer)
        else:
            print(f"Error: Username is null")

@client.command()
async def quit(ctx):
    client.close()

# join vc
@client.command()
async def join(ctx):
    global voice_channel
    if ctx.author.voice:
        channel = ctx.message.author.voice.channel
        try:
            await channel.connect()
        except Exception as e:
            print(e)
        voice_channel = ctx.guild.voice_client
        #Replace Sink for either StreamSink or WhisperSink
        queue = asyncio.Queue()
        loop.create_task(whisper_message(queue))
        whisper_sink = Sink(sink_settings=sink_settings, queue=queue, loop=loop)
        
        voice_channel.start_recording(whisper_sink, callback, ctx)
        await ctx.send("Joining.")
    else:
        await ctx.send("You are not in a VC channel.")

#When client stops recording, this is called
#Replace Sink for either StreamSink or WhisperSink
async def callback(sink: Sink, ctx):
    sink.close()

# leave vc
@client.command()
async def leave(ctx):
    global voice_channel
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        voice_channel = None
    else:
        await ctx.send("Not in VC.")

@client.event
async def on_ready():
    for guild in client.guilds:
            print(
                f'{client.user} is connected to the following guild:\n'
                f'{guild.name}(id: {guild.id})'
            )
    print(f"We have logged in as {client.user}")

@client.event
async def on_message(message : discord.Message):  
    #Ignore your own message
    if message.author == client.user:
            return
    
    #To ignore DMs
    if hasattr(message.channel, 'DMChannel'):
        print("Ignore DMS")
        return           
    
    if len(message.content) > 0:

        #! is a command message
        if message.content[0] == "!":
            
            if COMMAND_ROLES == [] and COMMANDS_USERS == []:
                await client.process_commands(message)
            elif message.author.id in COMMANDS_USERS:
                await client.process_commands(message)
            elif any(role.name in COMMAND_ROLES for role in message.author.roles):
                await client.process_commands(message)              
            return
        
        #If user @s or replies to your bot
        if (client.user in message.mentions or client.user in message.role_mentions):
          
            if REPLY_CHANNELS != [] and not any(message.channel.id == channel for channel in REPLY_CHANNELS):
                return

            text = message.content.replace(client.user.mention, '').strip()
            
            if message.author.nick is not None:
                username = message.author.nick.replace(".", " ")
            elif message.author.display_name is not None:
                username = message.author.display_name.replace(".", " ")
            else:
                username = message.author.name.replace(".", " ")

            response = await loop.run_in_executor(None, ai.chat, username, text)

            await message.reply(response, mention_author=False)

#Plays an audio file through discord. So far only audio files work, not streaming.
#TODO make voice_channel.play async. Probably need to use the callback feature.
async def play_audio(text):
    global voice_channel   
    if voice_channel is not None:      
        audio_file = await loop.run_in_executor(None, speech.tts_wav, text)
        if audio_file is not None:
            while voice_channel.is_playing():
                await asyncio.sleep(.1)
            prepared_audio = FFmpegOpusAudio(audio_file, executable="ffmpeg")
            voice_channel.play(prepared_audio)

#Stops the bot if they are speaking
@client.command()
async def stop(ctx):
    ctx.guild.voice_client.stop()

async def get_username(user_id):
    return await client.fetch_user(user_id)

client.run(TOKEN)