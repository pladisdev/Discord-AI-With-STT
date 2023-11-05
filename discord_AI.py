import asyncio

import discord
from discord.ext import commands
from discord import FFmpegOpusAudio

#from sinks.stream_sink import StreamSink #Outputs audio to desired output audio device (tested on windows)
from sinks.whisper_sink import WhisperSink #User whisper to transcribe audio and outputs to TTS

#You should replace these with your llm and tts of choice
#llm_dialo for fast but awful conversation
#llm_guan_3b for slow but better conversation
from modules import llm_guan_3b as llm, tts_windows as tts

TOKEN = "insert your discord bot token here"

#This is who you allow to use commands with the bot, either by role, user or both.
#can be a list, both being empty means anyone can command the bot. Roles should be lowercase, USERS requires user IDs
COMMAND_ROLES = []
COMMANDS_USERS = []

#Enter the channel IDs for which channels you want the bot to reply to users. Keep empty to allow all channels.
REPLY_CHANNELS = []

#OUTPUT_DEVICE = "your_audio_output_device" # for StreamSink only

loop = asyncio.get_event_loop()
intents = discord.Intents.all()
client = commands.Bot(command_prefix="!", intents=intents, loop=loop)

ai = llm.LLM()
speech = tts.TTS()
  
voice_channel = None

#In a seperate async thread, recieves messages from STT
async def whisper_message(queue : asyncio.Queue):
 while True:
    response = await queue.get()

    if response is None:
        break
    else:
        user_id = response["user"]
        text = response["result"]
                
        username = await get_username(user_id)  

        print(f"Detected Message: {text}")

        answer = await loop.run_in_executor(None, ai.chat, username, text)
        await play_audio(answer)

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
        whisper_sink = WhisperSink(queue, 
                                   loop,
                                   data_length=50000, 
                                   quiet_phrase_timeout=1.25, 
                                   mid_sentence_multiplier=1.75, 
                                   no_data_multiplier=0.75, 
                                   max_phrase_timeout=20, 
                                   min_phrase_length=3, 
                                   max_speakers=4)
        
        voice_channel.start_recording(whisper_sink, callback, ctx)
        await ctx.send("Joining.")
    else:
        await ctx.send("You are not in a VC channel.")

#When client stops recording, this is called
#Replace Sink for either StreamSink or WhisperSink
async def callback(sink: WhisperSink, ctx):
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