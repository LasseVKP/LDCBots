import discord
from vkp import BasicBot, EconomyDatabaseHandler, get_env_var


EDB = EconomyDatabaseHandler()

intents = discord.Intents().default()
intents.message_content = True

bot = BasicBot(intents=intents, debug_guilds=[769312138207559680])


@bot.slash_command()
async def hello(ctx: discord.ApplicationContext):
    EDB.add_balance(ctx.author, 1.5)
    await ctx.respond("Added 5 money")


@bot.slash_command()
async def balance(ctx: discord.ApplicationContext, user: discord.User = None):
    user_balance = EDB.get_balance(user) if user else EDB.get_balance(ctx.author)

    user_balance = user_balance if user_balance != int(user_balance) else int(user_balance)

    await ctx.respond(user_balance)


bot.run(get_env_var("ECONOMY_TOKEN"))
