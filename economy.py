import discord
from vkp import BasicBot, EconomyDatabaseHandler, get_env_var, floor, Blackjack, error_embed, simple_message_embed, format_money, format_tokens

# Create database handler
EDB = EconomyDatabaseHandler()

# Create a basic bot
bot = BasicBot(debug_guilds=[769312138207559680])

# Initialize blackjack
blackjack_object = Blackjack()


tokens = bot.create_group("token", "Token related commands")


# Pay user, command
@bot.slash_command()
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
@bot.slash_command()
async def balance(ctx: discord.ApplicationContext, user: discord.Member = None):

    # Check if a user is specified, else get author
    user = user or ctx.author

    user_balance = EDB.get_balance(user)

    # Send an int if the user doesn't have a number with decimal places
    user_balance = user_balance if user_balance != int(user_balance) else int(user_balance)

    # Create embed and if user is ctx author then write "You" instead of a username
    message = f"You currently have {format_money(user_balance)}"
    if user is ctx.author:
        message = f"{user.display_name} currently has {format_money(user_balance)}"

    embed = simple_message_embed(ctx.author, message)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

    await ctx.respond(embed=embed)


@bot.slash_command()
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


@bot.slash_command()
async def leaderboard(ctx: discord.ApplicationContext):
    embed = simple_message_embed(ctx.author, "Top 10 Leaderboard")
    current_leaderboard = EDB.get_leaderboard()
    for x in range(len(current_leaderboard)):
        user = current_leaderboard[x]
        embed.add_field(name=f"{x + 1} | {user['cached_name']}", value=f"{format_money(user['balance'])}")
    if len(current_leaderboard) == 0:
        embed.add_field(name="No users yet", value="_ _")
    await ctx.respond(embed=embed)


@tokens.command()
async def leaderboard(ctx: discord.ApplicationContext):
    await ctx.respond("token leaderboard placeholder")


@tokens.command()
async def balance(ctx: discord.ApplicationContext, user: discord.Member):

    # Check if a user is specified, else get author
    user = user or ctx.author

    user_balance = EDB.get_tokens(user)

    # Send an int if the user doesn't have a number with decimal places
    user_balance = user_balance if user_balance != int(user_balance) else int(user_balance)

    # Create embed and if user is ctx author then write "You" instead of a username
    message = f"You currently have {format_tokens(user_balance)}"
    if user is ctx.author:
        message = f"{user.display_name} currently has {format_tokens(user_balance)}"

    embed = simple_message_embed(ctx.author, message)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

    await ctx.respond(embed=embed)


@tokens.command()
async def buy(ctx: discord.ApplicationContext, amount: int):
    if amount < 1:
        await ctx.respond(embed=error_embed(ctx.author,
                                            f"You have to buy more than {format_tokens(0)}"),
                          ephemeral=True)
    
    await ctx.respond("Placeholder buy tokens")


@bot.slash_command()
async def money(ctx: discord.ApplicationContext, amount: float):
    EDB.add_balance(ctx.author, amount)
    await ctx.respond(f"You received {format_money(amount)}")


bot.run(get_env_var("ECONOMY_TOKEN"))
