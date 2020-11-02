
import asyncio
import discord
import datetime
from discord.utils import get
from discord.ext import commands
from secrets.txt import GUILD, TOKEN


leaderboard = dict()
userjoindict = dict()
userjoineddict = dict()
userdurationdict = dict()
intents = discord.Intents.all()

client = commands.Bot(command_prefix='/', intents=intents)


@client.event
async def on_ready():
    print('ready')


@client.event
async def on_voice_state_update(member, before, after):
    for guild in client.guilds:
        if guild.name == GUILD:
            break

    channelid = [channel.id for channel in guild.channels]

    if before.channel and after.channel:
        if (before.channel.id not in channelid or before.channel.id == get(guild.voice_channels, name='Gulag').id) and (
                after.channel.id in channelid and after.channel.id != get(guild.voice_channels, name='Gulag')
                .id):
            await start_tracking(member)
        if before.channel.id in channelid and (after.channel.id not in channelid or after.channel.id == get(guild.voice_channels, name='Gulag').id):
            await stop_tracking(member)

    if not before.channel and (after.channel and after.channel.id != get(guild.voice_channels, name='Gulag').id):
        await start_tracking(member)

    if before.channel and not after.channel:
        if before.channel.id != get(guild.voice_channels, name='Gulag').id:
            await stop_tracking(member)


@client.event
async def start_tracking(member: discord.Member):
    print('startedtracking')
    userjoineddict.update({member: '1'})
    userjoindict.update({member: datetime.datetime.now()})


@client.command()
async def time(cxt, *, member: discord.Member = None):
    if member is None:
        author = cxt.message.author
    else:
        author = member

    if userdurationdict.get(author) is None and userjoineddict.get(author) is None:
        time = 0
        await cxt.send('no time amk')

    elif userdurationdict.get(author) is not None and userjoineddict.get(author) == '0':
        time = userdurationdict.get(author)
        await cxt.send('{} has spent {} in a channel on this discord'.format(author.name, str(time)))

    elif userdurationdict.get(author) is not None and userjoineddict.get(author) == '1':
        t1 = datetime.datetime.now() - userjoindict.get(author)
        time = userdurationdict.get(author) + t1
        await cxt.send('{} has {} in a channel on this discord'.format(author.name, str(time)))

    elif userdurationdict.get(author) is None and userjoineddict.get(author) == '1':
        time = datetime.datetime.now() - userjoindict.get(author)
        await cxt.send('{} has spent {} in a channel on this discord'.format(author.name, str(time)))


@client.command()
async def place(cxt, *, place: discord.Member = None):
    for guild in client.guilds:
        if guild == GUILD:
            break
    for member in guild.members:
        if userdurationdict.get(member) is None and userjoineddict.get(member) is None:
            leaderboard.update({member.name: 0})
        elif userdurationdict.get(member) is not None and userjoineddict.get(member) == '0':
            time = userdurationdict.get(member)
            leaderboard.update({member.name: time.total_seconds()})
        elif userdurationdict.get(member) is not None and userjoineddict.get(member) == '1':
            t1 = datetime.datetime.now() - userjoindict.get(member)
            time = userdurationdict.get(member) + t1
            leaderboard.update({member.name: time.total_seconds()})
        elif userdurationdict.get(member) is None and userjoineddict.get(member) == '1':
            time = datetime.datetime.now() - userjoindict.get(member)
            leaderboard.update({member.name: time.total_seconds()})
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    if place is None:
        search = cxt.message.author.name
    else:
        search = str(place.name)
    i = 0
    for x in sorted_lb:
        i += 1
        if x[0] == search:
            t = int(x[1])
            time = str(datetime.timedelta(seconds=t))
            await cxt.send('Your searched member is place {} with a time of {}'.format(i, time))
            break
    sorted_lb.clear()
    leaderboard.clear()


@client.command()
async def top(cxt, *, num: int = None):
    if num is None:
        await cxt.send('Please enter a number. For example "top 10" to se the top 10')
        return
    for guild in client.guilds:
        if guild == GUILD:
            break
    for member in guild.members:
        if userdurationdict.get(member) is None and userjoineddict.get(member) is None:
            leaderboard.update({member.name: 0})
        elif userdurationdict.get(member) is not None and userjoineddict.get(member) == '0':
            time = userdurationdict.get(member)
            leaderboard.update({member.name: time.total_seconds()})
        elif userdurationdict.get(member) is not None and userjoineddict.get(member) == '1':
            t1 = datetime.datetime.now() - userjoindict.get(member)
            time = userdurationdict.get(member) + t1
            leaderboard.update({member.name: time.total_seconds()})
        elif userdurationdict.get(member) is None and userjoineddict.get(member) == '1':
            time = datetime.datetime.now() - userjoindict.get(member)
            leaderboard.update({member.name: time.total_seconds()})
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    i = 0
    for x in sorted_lb:
        i += 1
        time = datetime.timedelta(seconds=int(x[1]))
        await cxt.send('{}. {} with a time of {}'.format(i, x[0], time))
        if i == num:
            return


@client.command()
async def timeboard(cxt, *, num: int = None):
    if num is None:
        await cxt.send('Please enter a number. For example "top 10" to se the top 10')
        return
    for guild in client.guilds:
        if guild == GUILD:
            break
    for member in guild.members:
        if userdurationdict.get(member) is None and userjoineddict.get(member) is None:
            leaderboard.update({member.name: 0})
        elif userdurationdict.get(member) is not None and userjoineddict.get(member) == '0':
            time = userdurationdict.get(member)
            leaderboard.update({member.name: time.total_seconds()})
        elif userdurationdict.get(member) is not None and userjoineddict.get(member) == '1':
            t1 = datetime.datetime.now() - userjoindict.get(member)
            time = userdurationdict.get(member) + t1
            leaderboard.update({member.name: time.total_seconds()})
        elif userdurationdict.get(member) is None and userjoineddict.get(member) == '1':
            time = datetime.datetime.now() - userjoindict.get(member)
            leaderboard.update({member.name: time.total_seconds()})
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    i = 0
    for x in sorted_lb:
        i += 1
        time = datetime.timedelta(seconds=int(x[1]))
        await cxt.send('{}. {} with a time of {}'.format(i, x[0], time))
        if i == num:
            return


@client.event
async def checking():
    while True:
        if datetime.datetime.now().minute == 30:
            with open('save.txt', 'w') as f:
                f.write(str(userdurationdict))
                f.close()
        await asyncio.sleep(2)


@client.event
async def stop_tracking(member: discord.Member):
    userjoineddict.update({member: '0'})
    duration = datetime.datetime.now() - userjoindict.get(member)
    if member in userdurationdict:
        newduration = userdurationdict.get(member) + duration
        userdurationdict.update({member: newduration})
    elif member not in userdurationdict:
        userdurationdict.update({member: duration})
    print('stoppedtracking')
    print(userdurationdict.get(member))


client.run(TOKEN)
client.loop.create_task(checking())