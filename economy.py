import discord, datetime
from discord.ext import tasks
from vkp import (BasicBot, EconomyDatabaseHandler, get_env_var, floor, Blackjack, error_embed, simple_message_embed,
                 format_money, format_tokens, Default, DailyView)

# Create database handler
EDB = EconomyDatabaseHandler()

# Create a basic bot
bot = BasicBot(debug_guilds=[769312138207559680])

# Initialize blackjack
blackjack_object = Blackjack()


tokens = bot.create_group("token", "Commands related to the token economy")


utc = datetime.timezone.utc
midnight = datetime.time(hour=23, minute=0, second=0, tzinfo=utc)


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


@bot.slash_command(description="Play blackjack")
async def blackjack(ctx: discord.ApplicationContext, amount: int):
    amount = floor(amount, 2)

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


# Start the bot
bot.run(get_env_var("ECONOMY_TOKEN"))
