import discord
from discord.ext import tasks
import time
import re
from timeit import default_timer
import pandas as pd
import requests
from constants import REFORGES, LOWEST_PERCENT_MARGIN, LOWEST_PRICE, CHANNEL_ID, DEBUG, HC_ADMINS
from bot_token import TOKEN
import signal
import asyncio
import multiprocessing
from multiprocessing import Queue
import sys

# connect discord bot to channel
# client = commands.Bot(command_prefix = '.')
client = discord.Client()

cumPipe = Queue()

# ctrl + C unscrewing
signal.signal(signal.SIGINT, signal.SIG_DFL)

def fetchPage(session, page):
    # generate return type
    returnData = []
    base_url = "https://api.hypixel.net/skyblock/auctions?page="
    # download with a session (passed to object)
    with session.get(base_url + page) as response:
        # debug pring
        if (DEBUG): print("Fetching Page " + page)
        # puts response in a dict
        data = response.json()
        if data['success']:
            totalPages = data['totalPages']
            for auction in data['auctions']:
                if not auction['claimed'] and 'bin' in auction and not "Furniture" in auction["item_lore"]: # if the auction isn't a) claimed and is b) BIN
                    # removes level if it's a pet, also
                    index = re.sub("\[[^\]]*\]", "", auction['item_name']) # + auction['tier']
                    # removes reforges and other yucky characters
                    # Vlad: inefficient but fkit 
                    for reforge in REFORGES: index = index.replace(reforge, "")
                    # clean up the index some more
                    index = index.strip().lower()
                    # add to the return object
                    returnData.append({
                        "id": auction['uuid'],
                        "name": auction['item_name'],
                        "index": index,
                        "cost": auction['starting_bid']
                    })

        return (returnData, totalPages)

def get_data_sync():
    # fetch page 0 of auctions
    c = requests.get("https://api.hypixel.net/skyblock/auctions?page=0")
    # convert page from str to *JSON
    resp = c.json()

    lastUpdated = resp['lastUpdated']
    totalPages = resp['totalPages']

    data = [] # create new data boject
    with requests.Session() as sess:
        for x in range(1, totalPages):
            returnData, newTotalPages = fetchPage(sess, str(x))
            data += returnData[:]
            if (totalPages != newTotalPages): print("WUT?????")
    if (DEBUG): print(len(data))
    return (data, lastUpdated)

def flip(cumPipeC):
    # Resets variables
    START_TIME = default_timer()

    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    # future = asyncio.ensure_future(get_data_asynchronous())
    # loop.run_until_complete(future)

    # use sync method instead of async
    data, lastUpdated = get_data_sync()

    # generate a price map
    priceMap = {}
    for item in data:
        try:
            if priceMap[item["index"]]:
                # item exists in indexes, check values
                if item["cost"] < priceMap[item["index"]]["cheapest"]["cost"]:
                    # the first item is guerenteed, if it exists, check the price
                    # if cheaper, move it to second and the new item to first
                    priceMap[item["index"]]["second"] = priceMap[item["index"]]["cheapest"]
                    priceMap[item["index"]]["cheapest"] = item
                elif priceMap[item["index"]]["second"]:
                    # if the upper condition isn't met and a second item exists,
                    # check its price, and if the new item is cheaper, write it down
                    if item["cost"] < priceMap[item["index"]]["second"]["cost"]:
                        priceMap[item["index"]]["second"] = item
                else:
                    # second item doesn't exist, just write the new object to the second item
                    priceMap[item["index"]]["second"] = item
        except KeyError:
            # item doesn't exist, create a new index value
            priceMap[item["index"]] = {
                "cheapest": item,
                "second": None
            }
    # print(priceMap)

    # Check for profitable objects that can be shown
    worthIt = []
    if len(data) > 0:
        for key in priceMap:
            item = priceMap[key]
            #   The cost of the cheapest item is greater &  a second item   &        margins are good
            #   then the LOWEST_PRICE constant           &  exists          &
            if (item["cheapest"]["cost"] > LOWEST_PRICE and item["second"] and ((item["second"]["cost"] - item["cheapest"]["cost"]) / item["cheapest"]["cost"]) > LOWEST_PERCENT_MARGIN):
                worthIt.append(item)

    if len(worthIt): # if there's results to print
        if (DEBUG): print("found {0} worth it items".format(len(worthIt)))
        # df = pd.DataFrame(['/viewauction ' + str(max(results, key=lambda entry:entry[1])[0][0])])
        # df.to_clipboard(index=False,header=False) # copies most valuable auction to clipboard (usually just the only auction cuz very uncommon for there to be multiple

        done = default_timer() - START_TIME

        for item in worthIt:
            cheapest = item["cheapest"]
            second = item["second"]
            msg = "/viewauction {} | Item Name: {} | Item price: {:,} | Second lowest BIN: {:,} | Time to refresh AH: {}".format(cheapest['id'], cheapest['name'], cheapest['cost'], second['cost'], str(round(done, 2)))
            # get channel reference
            cumPipeC.put(msg)
            if (DEBUG): print(msg)
        # print("\nLooking for auctions...")
        return lastUpdated

def flipTimeCheckInvoker(lastUpdated, cumPipeC):
    # if 60 seconds have passed since the last update
    if time.time()*1000 > lastUpdated + 60000:
        if (DEBUG): print("Checking for new items to be listed")
        lastUpdated = flip(cumPipeC)
    else:
        if (DEBUG): print("wait some more")
    
    return lastUpdated

def executeCooming(cumPipeC):
    lastUpdated = flip(cumPipeC)

    while True:
        lastUpdated = flipTimeCheckInvoker(lastUpdated, cumPipeC)
        time.sleep(60) # wait 60 seconds between checks

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

    channel = client.get_channel(CHANNEL_ID)
    await channel.send("Looking for auctions...")
    

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('$coom'):
        await message.channel.send('Coom!')

    if message.content.startswith('$term'):
        if (message.author.id in HC_ADMINS):
            await message.channel.send("This command sucks, it may work, it may not, lets try")
            client.logout()
            client.close()
            sys.exit()
        else:
            await message.channel.send("nuuuuuu, ban")

# @tasks.loop(seconds=1)
async def checkCumPipe(cumPipeC):
    while True:
        # very gd verbose
        # if (DEBUG): print("Checking the cumpipe", cumPipeC.empty())
        if (not cumPipeC.empty()):
            # get channel
            channel = client.get_channel(CHANNEL_ID)
            # send intro message
            await channel.send("New items found")
            # text storage
            text = ""
            # for every message in the queue
            while not cumPipeC.empty():
                # grab the queue message
                message = cumPipeC.get()
                # print the message to console
                if (DEBUG): print(message)
                # check if the message is to long
                if (len(text) + len(message) >= 2000):
                    await channel.send(text)
                    text = ""
                text += message + "\n"
            if (text):
                await channel.send(text)
        await asyncio.sleep(1)

client.loop.create_task(checkCumPipe(cumPipe))

def start():
    p = multiprocessing.Process(target=executeCooming, args=(cumPipe,))
    p.start()
    client.run(TOKEN)

if __name__ == "__main__":
    start()
