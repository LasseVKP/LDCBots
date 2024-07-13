import os
import random
import discord
from vkp import (BasicBot, error_embed, simple_message_embed, Default)

# Create bot
bot = BasicBot(debug_guilds=[os.getenv("GUILD")])


@bot.slash_command(description="Ask the 8ball a question")
async def eightball(ctx: discord.ApplicationContext, question: str):

    embed = simple_message_embed(ctx.author, f"\🎱 | {question[:200]}")
    embed.description = random.choice(Default.EIGHTBALL_RESPONSES)
    embed.color = Default.BLACK

    await ctx.respond(embed=embed)


bot.run(os.getenv("GENERAL_TOKEN"))
