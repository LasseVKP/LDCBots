import discord
from vkp import BasicBot, EconomyDatabaseHandler, get_env_var, floor, Blackjack


# Create database handler
EDB = EconomyDatabaseHandler()

# Create a basic bot
bot = BasicBot(debug_guilds=[769312138207559680])

# Initialize blackjack
blackjack_object = Blackjack()


# Pay user, command
@bot.slash_command()
async def pay(ctx: discord.ApplicationContext, user: discord.User, amount: float):

    # Check if user is a member of the guild
    if not ctx.guild.get_member(user.id):
        await ctx.respond("Specified member doesn't exist in this discord server", ephemeral=True)
        return

    # Check if user receiving money is a bot
    if user.bot:
        await ctx.respond("You cannot pay a bot", ephemeral=True)
        return

    # Check if amount is more than 0
    amount = floor(amount, 2)
    if amount <= 0:
        await ctx.respond("You have to pay more than 0", ephemeral=True)
        return

    # Check if user has enough money
    if amount < EDB.get_balance(ctx.author):
        await ctx.respond("Insufficient funds", ephemeral=True)
        return

    # Transfer money
    EDB.add_balance(ctx.author, -amount)
    EDB.add_balance(user, amount)

    await ctx.respond(f"Paid {user.display_name}, {amount}")


# Check user balance, command
@bot.slash_command()
async def balance(ctx: discord.ApplicationContext, user: discord.User = None):
    # Check if a user is specified, else get author balance
    user_balance = EDB.get_balance(user) if user else EDB.get_balance(ctx.author)

    # Send an int if the user doesn't have a number with decimal places
    user_balance = user_balance if user_balance != int(user_balance) else int(user_balance)

    await ctx.respond(user_balance)


@bot.slash_command()
async def blackjack(ctx: discord.ApplicationContext, amount: float):
    amount = floor(amount, 2)

    #  Make sure user can't bet less than 0
    if amount < 0:
        await ctx.respond("You have to bet more than 0", ephemeral=True)
        return

    # Make sure user has enough money
    if EDB.get_balance(ctx.author) < amount:
        await ctx.respond("Insufficient funds", ephemeral=True)
        return

    # Create a view and embed and send it
    blackjack_view = blackjack_object.create_view(ctx.author, amount, EDB)
    await ctx.respond(embed=blackjack_view.embed, view=blackjack_view)

    # Remove amount from user balance to make sure they can't open multiple blackjacks with non-existent money
    EDB.add_balance(ctx.author, -amount)


bot.run(get_env_var("ECONOMY_TOKEN"))
