import json
import os
import math
import random
import discord, datetime
from discord.ext import tasks
from vkp import (BasicBot, EconomyDatabaseHandler, get_env_var, floor, Blackjack, error_embed, simple_message_embed,
                 format_money, format_tokens, Default, DailyView, get_day, calc_pet_level, calc_next_pet_level_xp, get_minute, is_pet_alive)

# Create database handler
EDB = EconomyDatabaseHandler()

# Create a basic bot
bot = BasicBot(debug_guilds=[os.getenv("GUILD")])

# Initialize blackjack
blackjack_object = Blackjack()


tokens = bot.create_group("token", "Commands related to the token economy")
pets = bot.create_group("pet", "Commands related to pets")

midnight = datetime.time(hour=22, minute=0, second=0)


# Run a loop at midnight
@tasks.loop(time=midnight)
async def midnight_loop():
    if datetime.datetime.today().weekday() == 0:
        # Get bot announcement channel to send message in
        guild = await bot.fetch_guild(Default.GUILD)
        channel = await guild.fetch_channel(Default.ANNOUNCEMENTS_CHANNEL)

        # Reset token balances and pool and get the winners
        winners, pool = EDB.reset_tokens()

        # Check if there were any winners
        if len(winners) == 0:
            # Send message
            embed = simple_message_embed(user=bot.user,
                                         message="A week has passed but the token pool was empty, so no tokens were distributed!")
            await channel.send(embed=embed)
            return

        # Create embed
        embed = simple_message_embed(user=bot.user, message="A week has passed so the Token pool has been distributed")
        embed.description = (f"{format_tokens(pool)} was bought this week, "
                             f"meaning {format_money(floor(pool*Default.TOKEN_VALUE, 2))} "
                             f"will be distributed amongst the top {len(winners)} on the token leaderboard!")

        # Create a field per winner
        for x in range(len(winners)):
            amount = winners[x]['reward']
            cached_name = winners[x]['name']
            embed.add_field(name=f"{x+1} | {cached_name}", value=f"Received {format_money(amount)}", inline=False)

        # Send message
        await channel.send(embed=embed)


# Pay user, command
@bot.slash_command(description="Pay a user")
async def pay(ctx: discord.ApplicationContext, user: discord.Member, amount: float):
    # Check if user is a member of the guild
    if not ctx.guild.get_member(user.id):
        await ctx.respond(embed=error_embed(ctx.author,
                                      "Specified member doesn't exist in this discord server"), ephemeral=True)
        return

    # Check if user receiving money is a bot
    if user.bot:
        await ctx.respond(embed=error_embed(ctx.author,
                                      "You cannot pay a bot"), ephemeral=True)
        return

    # Check if amount is more than 0
    amount = floor(amount, 2)
    if amount <= 0:
        await ctx.respond(embed=error_embed(ctx.author,
                                      f"You have to pay more than {format_money(0)}"), ephemeral=True)
        return

    # Check if user has enough money
    if amount > EDB.get_balance(ctx.author):
        await ctx.respond(embed=error_embed(ctx.author,
                                      "Insufficient funds"),
                          ephemeral=True)
        return

    # Transfer money
    EDB.add_balance(ctx.author, -amount)
    EDB.add_balance(user, amount)

    embed = simple_message_embed(ctx.author, f"Paid {user.display_name} {format_money(amount)}")
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

    await ctx.respond(embed=embed)


# Check user balance, command
@bot.slash_command(description="See a user's balance")
async def balance(ctx: discord.ApplicationContext, user: discord.Member = None):

    # Check if a user is specified, else get author
    user = user or ctx.author

    user_balance = EDB.get_balance(user)

    # Create embed and if user is ctx author then write "You" instead of a username
    message = f"You currently have {format_money(user_balance)}"
    if user is not ctx.author:
        message = f"{user.display_name} currently has {format_money(user_balance)}"

    embed = simple_message_embed(ctx.author, message)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

    await ctx.respond(embed=embed)


@bot.slash_command(description="See the leaderboard")
async def leaderboard(ctx: discord.ApplicationContext):
    embed = simple_message_embed(ctx.author, f"Top {Default.CURRENCY} Leaderboard")
    current_leaderboard = EDB.get_leaderboard()
    for x in range(len(current_leaderboard)):
        user = current_leaderboard[x]
        embed.add_field(name=f"{x + 1} | {user['cached_name']}", value=f"{format_money(user['balance'])}", inline=False)
    if len(current_leaderboard) == 0:
        embed.add_field(name="No users yet", value="_ _", inline=False)
    await ctx.respond(embed=embed)


@bot.slash_command(description="See the dailies")
async def daily(ctx: discord.ApplicationContext):
    view = None
    if not EDB.is_daily_claimed(ctx.author):
        view = DailyView(ctx.author, EDB)

    embed = simple_message_embed(ctx.author, "Dailies forecast")

    dailies = EDB.get_dailies()

    for x in range(len(dailies)):
        day = dailies[x]
        title = f"In {x+1} days" if x > 1 else "Tomorrow" if x == 1 else "Today"
        embed.add_field(name=title, value=f"{format_money(day['money'])} and {format_tokens(day['tokens'])}", inline=False)

    await ctx.respond(embed=embed, view=view)


# Token related commands

@bot.slash_command(description="Play blackjack")
async def blackjack(ctx: discord.ApplicationContext, amount: int):

    #  Make sure user can't bet less than 0
    if amount <= 0:
        await ctx.respond(embed=error_embed(ctx.author,
                                            f"You have to bet more than {format_tokens(0)}"),
                          ephemeral=True)
        return

    # Make sure user has enough money
    if EDB.get_tokens(ctx.author) < amount:
        await ctx.respond(embed=error_embed(ctx.author,
                                            "Insufficient funds"),
                          ephemeral=True)
        return

    # Create a view and embed and send it
    blackjack_view = blackjack_object.create_view(ctx.author, amount, EDB)
    await ctx.respond(embed=blackjack_view.embed, view=blackjack_view)

    # Remove amount from user balance to make sure they can't open multiple blackjacks with non-existent money
    EDB.add_tokens(ctx.author, -amount)


@tokens.command(description="See the token leaderboard")
async def leaderboard(ctx: discord.ApplicationContext):
    embed = simple_message_embed(ctx.author, f"Top {Default.TOKENS} Leaderboard")
    current_leaderboard = EDB.get_token_leaderboard()
    for x in range(len(current_leaderboard)):
        user = current_leaderboard[x]
        embed.add_field(name=f"{x + 1} | {user['cached_name']}", value=f"{format_tokens(user['tokens'])}", inline=False)
    if len(current_leaderboard) == 0:
        embed.add_field(name="No users yet", value="_ _", inline=False)
    await ctx.respond(embed=embed)


@tokens.command(description="See a user's token balance")
async def balance(ctx: discord.ApplicationContext, user: discord.Member = None):

    # Check if a user is specified, else get author
    user = user or ctx.author

    user_balance = EDB.get_tokens(user)

    # Create embed and if user is ctx author then write "You" instead of a username
    message = f"You currently have {format_tokens(user_balance)}"
    if user is not ctx.author:
        message = f"{user.display_name} currently has {format_tokens(user_balance)}"

    embed = simple_message_embed(ctx.author, message)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

    await ctx.respond(embed=embed)


@tokens.command(description="Buy tokens")
async def buy(ctx: discord.ApplicationContext, amount: int):
    if amount < 1:
        await ctx.respond(embed=error_embed(ctx.author,
                                            f"You have to buy more than {format_tokens(0)}"),
                          ephemeral=True)
        return
    if amount*Default.TOKEN_VALUE > EDB.get_balance(ctx.author):
        await ctx.respond(embed=error_embed(ctx.author,
                                            "Insufficient funds"),
                          ephemeral=True)
        return
    tokens_bought = EDB.get_tokens_bought(ctx.author)
    if amount + tokens_bought > Default.MAX_WEEKLY_TOKENS:
        await ctx.respond(embed=error_embed(ctx.author,
                                            f"You can only buy {format_tokens(Default.MAX_WEEKLY_TOKENS-tokens_bought)} more this week!"),
                          ephemeral=True)
        return

    EDB.add_balance(ctx.author, -amount*Default.TOKEN_VALUE)
    EDB.add_tokens(ctx.author, amount, True)
    EDB.add_token_pool(amount)

    embed = simple_message_embed(ctx.author,
                                 f"Bought {format_tokens(amount)} for {format_money(floor(amount*Default.TOKEN_VALUE, 2))}")
    embed.description = f"{format_tokens(amount)} were added to the token pool"
    await ctx.respond(embed=embed)


@tokens.command(description="See this week's token pool")
async def pool(ctx: discord.ApplicationContext):
    token_pool = EDB.get_token_pool()
    await ctx.respond(embed=simple_message_embed(ctx.author, f"Current token pool is {format_tokens(token_pool)} "
                                                             f"which is worth {format_money(token_pool*Default.TOKEN_VALUE)}"))


@tokens.command(description="Gamble on a dice roll")
async def diceroll(ctx: discord.ApplicationContext, amount: int):

    #  Make sure user can't bet less than 0
    if amount <= 0:
        await ctx.respond(embed=error_embed(ctx.author,
                                            f"You have to bet more than {format_tokens(0)}"),
                          ephemeral=True)
        return

    # Make sure user has enough money
    if EDB.get_tokens(ctx.author) < amount:
        await ctx.respond(embed=error_embed(ctx.author,
                                            "Insufficient funds"),
                          ephemeral=True)
        return

    winnings = amount

    result = random.randint(1, 6)

    embed = simple_message_embed(ctx.author, f"\🎲 The dice rolled {result} \🎲")
    embed.set_thumbnail(url=Default.DICE_IMAGES[result - 1])

    if result > 4:
        winnings *= 0.5 if result == 5 else 1
        winnings = math.ceil(winnings)
        embed.description = f"Which means you won {winnings} {Default.TOKENS}"
    elif result == 4:
        winnings = 0
        embed.description = "Which means you got your tokens back"
    else:
        embed.description = f"Which means you lost {winnings} {Default.TOKENS}"
        winnings *= -1

    # Create an embed and send it
    await ctx.respond(embed=embed)

    # Remove amount from user balance to make sure they can't open multiple blackjacks with non-existent money
    EDB.add_tokens(ctx.author, winnings)


@pets.command(description="Show pets that are available for adoption")
async def shelter(ctx: discord.ApplicationContext):
    available_pets = EDB.get_pets()

    embed = simple_message_embed(ctx.author, "Pets currently available to be adopted")

    for idx, pet in enumerate(available_pets):
        level = calc_pet_level(pet['xp'])

        embed.add_field(name=f"{idx+1} | {pet['name']} the {pet['type']}", value=f"\\🔹 Age: {floor(pet['age']/7, 1)} years\n\\🔹 Pet level: {level}\n\\🔹 Price: {format_money(pet['price'])}")

    await ctx.respond(embed=embed)


@pets.command(description="Preview a pet before adopting it")
async def preview(ctx: discord.ApplicationContext, index: int):
    available_pets = EDB.get_pets()
    if index < 1 or index > len(available_pets) + 1:
        await ctx.respond(embed=error_embed(ctx.author,
                                            f"Index out of range. Index has to be an integer between 1-{len(available_pets)}"),
                          ephemeral=True)
        return

    pet = available_pets[index - 1]

    with open("data/templates/petImages.json", "r") as f:
        pet_image = json.load(f)[pet["image"]]

    with open("data/templates/petTemplates.json", "r") as f:
        lifespan = floor(json.load(f)[pet['type']]['maxAge']/7, 1)

    embed = simple_message_embed(ctx.author, f"{index} | {pet['name']}")

    level = calc_pet_level(pet['xp'])
    next_level_xp = calc_next_pet_level_xp(level)

    embed.description = f"\\💠{pet['name']} is a {floor(pet['age'] / 7, 1)} year old {pet['type'].lower()}. \n\\💠A {pet['type'].lower()}s lifespan is {lifespan} years\n\n\\💠 Pet level: {level}\n\\💠Pet xp: {pet['xp']}/{next_level_xp}, needs {round(next_level_xp-pet['xp'], 1)} xp to level up\n\nIt costs {format_money(pet['price'])} to adopt {pet['name']}"
    embed.set_thumbnail(url=pet_image)

    await ctx.respond(embed=embed)


@pets.command(description="View a person's pet")
async def show(ctx: discord.ApplicationContext, user: discord.Member = None):
    user = user if user else ctx.author

    pet = EDB.get_pet(user)

    if not pet:
        await ctx.respond(embed=error_embed(ctx.author, "{0} own a pet".format(
            f"{user.display_name} doesn't" if user.id != ctx.author.id else "You don't")), ephemeral=True)
        return

    alive = await is_pet_alive(ctx, pet, EDB)

    if not alive:
        return

    with open("data/templates/petImages.json", "r") as f:
        pet_image = json.load(f)[pet["image"]]

    with open("data/templates/petTemplates.json", "r") as f:
        template = json.load(f)[pet['type']]

    age = floor((get_day()-pet['born'])/7, 1)
    lifespan = floor(template['maxAge']/7,1)
    level = calc_pet_level(pet['xp'])
    next_level_xp = calc_next_pet_level_xp(level)
    xp_for_next_level = round(next_level_xp - pet['xp'], 1)

    last_fed_time = get_minute() - pet['lastFed']
    hunger_state = "Not hungry" if last_fed_time < 120 else "Slightly hungry" if last_fed_time < 240 else "Hungry" if last_fed_time < 1080 else "Very hungry" if last_fed_time < 2160 else "Starving"


    embed = simple_message_embed(ctx.author,f"{pet['name']} the {pet['type']}")
    embed.description = "\\🎂 {8} is {0} years old. A {1}s lifespan is {2} years\n\n\\🍖 **Hunger:** {7}\n\n\\💠 **Pet level:** {3}\n\\💠 **Pet xp:** {4}/{5}, needs {6} xp to level up".format(age,
                                                                                                                                                            pet['type'].lower(),
                                                                                                                                                            lifespan,
                                                                                                                                                            level,
                                                                                                                                                            round(pet['xp'],1),
                                                                                                                                                            next_level_xp,
                                                                                                                                                            xp_for_next_level,
                                                                                                                                                            hunger_state,
                                                                                                                                                            pet['name'])
    embed.set_thumbnail(url=pet_image)

    await ctx.respond(embed=embed)


@pets.command()
async def rename(ctx: discord.ApplicationContext, new_name: str):
    pet = EDB.get_pet(ctx.author)

    if not pet:
        await ctx.respond(embed=error_embed(ctx.author, "You don't own a pet"), ephemeral=True)
        return

    alive = await is_pet_alive(ctx, pet, EDB)

    if not alive:
        return

    if len(new_name) > 28:
        await ctx.respond(embed=error_embed(ctx.author, "New name can't be longer than 28 characters"), ephemeral=True)
        return

    EDB.rename_pet(ctx.author, new_name.title())

    await ctx.respond(embed=simple_message_embed(ctx.author, f"Renamed {pet['name']}, to {new_name.title()}"))


@pets.command(description="Adopt a pet")
async def adopt(ctx: discord.ApplicationContext, index: int):
    if EDB.get_pet(ctx.author):
        await ctx.respond(embed=error_embed(ctx.author, "You can't adopt more than one pet"), ephemeral=True)
        return

    available_pets = EDB.get_pets()
    if index<1 or index> len(available_pets)+1:
        await ctx.respond(embed=error_embed(ctx.author, f"Index out of range. Index has to be an integer between 1-{len(available_pets)}"), ephemeral=True)
        return

    pet = available_pets[index-1]

    if pet['price'] > EDB.get_balance(ctx.author):
        await ctx.respond(embed=error_embed(ctx.author, f"You don't have enough {Default.CURRENCY} to buy {pet['name']} the {pet['type']}"), ephemeral=True)
        return

    with open("data/templates/petImages.json", "r") as f:
        pet_image = json.load(f)[pet["image"]]

    EDB.set_pet(ctx.author, pet)
    EDB.replace_pet(index - 1)
    EDB.add_balance(ctx.author, -pet['price'])

    embed = simple_message_embed(ctx.author, f"You adopted {pet['name']} the {pet['type']} for {format_money(pet['price'])}")
    embed.description = f"{pet['name']} is probably a bit hungry, so you can start off by using `/pet feed` to feed {pet['name']}"
    embed.set_thumbnail(url=pet_image)

    await ctx.respond(embed=embed)


@pets.command(description="")
async def feed(ctx: discord.ApplicationContext):
    pet = EDB.get_pet(ctx.author)

    if not pet:
        await ctx.respond(embed=error_embed(ctx.author, "You don't own a pet"), ephemeral=True)
        return

    alive = await is_pet_alive(ctx, pet, EDB)

    if not alive:
        return

    time_passed = get_minute()-pet['lastFed']

    if time_passed < 120:
        await ctx.respond(embed=error_embed(ctx.author, f"{pet['name']} isn't hungry yet. You can feed {pet['name']} again in {120-time_passed} minutes"), ephemeral=True)
        return

    with open("data/templates/petImages.json", "r") as f:
        pet_image = json.load(f)[pet["image"]]

    xp = round(random.random()*250+250, 1)

    EDB.feed_pet(ctx.author)
    EDB.add_pet_xp(ctx.author, xp)

    embed = simple_message_embed(ctx.author, f"You fed {pet['name']}")
    embed.description = f"{pet['name']} gained {xp} xp\n{pet['name']} now has {round(pet['xp']+xp,1)} xp"

    level = calc_pet_level(pet['xp'])
    new_level = calc_pet_level(round(pet['xp']+xp,1))

    if new_level > level:
        embed.description += f"\n🎉 {pet['name']} has reached level {new_level} 🎉"


    embed.set_thumbnail(url=pet_image)

    await ctx.respond(embed=embed)


@pets.command(description="Send your pet on a small adventure")
async def explore(ctx: discord.ApplicationContext):
    pet = EDB.get_pet(ctx.author)

    if not pet:
        await ctx.respond(embed=error_embed(ctx.author, "You don't own a pet"), ephemeral=True)
        return

    alive = await is_pet_alive(ctx, pet, EDB)

    if not alive:
        return

    time_passed = get_minute() - pet['lastFed']

    if time_passed >= 120:
        await ctx.respond(embed=error_embed(ctx.author, f"{pet['name']} is too hungry to explore right now. You can use `/pet feed` to feed {pet['name']}"), ephemeral=True)
        return

    time_passed = get_minute()-pet['lastBigAction']

    if time_passed < 60:
        await ctx.respond(embed=error_embed(ctx.author, f"{pet['name']} is too tired right now. You can send {pet['name']} on another adventure in {60-time_passed} minutes"), ephemeral=True)
        return

    with open("data/templates/petImages.json", "r") as f:
        pet_image = json.load(f)[pet["image"]]

    with open("data/templates/petAdventures.json", "r") as f:
        adventure = random.choice(json.load(f)[pet['type']])

    xp = round(random.random() * adventure['xpRange'] + adventure['minXp'], 1)


    EDB.use_pet_big_action(ctx.author)
    EDB.add_pet_xp(ctx.author, xp)


    embed = simple_message_embed(ctx.author, f"You sent {pet['name']} on a small adventure")
    embed.description = f"{pet['name']} {adventure['message']}"
    embed.description += f"\n{pet['name']} gained {xp} xp\n{pet['name']} now has {round(pet['xp']+xp,1)} xp"

    level = calc_pet_level(pet['xp'])
    new_level = calc_pet_level(round(pet['xp']+xp,1))

    if new_level > level:
        embed.description += f"\n🎉 {pet['name']} has reached level {new_level} 🎉"

    reward = round(random.random() * adventure['rewardRange'] + adventure['minReward'], 1)
    EDB.add_balance(ctx.author, reward)

    embed.description += f"\n\nYou got {reward}{Default.CURRENCY}"


    embed.set_thumbnail(url=pet_image)

    await ctx.respond(embed=embed)


@pets.command(description="Abandon your pet. Warning, there is no confirmation box")
async def abandon(ctx: discord.ApplicationContext):
    pet = EDB.get_pet(ctx.author)

    if not pet:
        await ctx.respond(embed=error_embed(ctx.author, "You don't own a pet"), ephemeral=True)
        return

    alive = await is_pet_alive(ctx, pet, EDB)

    if not alive:
        return

    EDB.remove_pet(ctx.author)
    await ctx.respond(embed=simple_message_embed(ctx.author, f"You abandoned your pet: {pet['name']} the {pet['type']}\n:("))


midnight_loop.start()

# Start the bot
bot.run(get_env_var("ECONOMY_TOKEN"))
