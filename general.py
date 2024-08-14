import json
import random
import discord
from vkp import (BasicBot, error_embed, simple_message_embed, Default, simple_embed, text_wrap, generate_discord_screenshot)
from moviepy.editor import *
import numpy

# Create bot
bot = BasicBot(debug_guilds=[os.getenv("GUILD")])

roles = json.load(open("data/templates/roles.json", "r", encoding="utf8"))


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if "custom_id" in interaction.data.keys():
        arguments = interaction.data["custom_id"].split(",")

        # If role related
        if arguments[0] == "roles":
            role = interaction.guild.get_role(int(arguments[3]))
            print(int(arguments[3]))
            print(role)

            # Remove role if user already has it
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(embed=simple_message_embed(user=interaction.user, message=f":x: Removed the \"{role.name}\" role from you"), ephemeral=True)

                return

            if arguments[1] == "one":
                global roles
                remove_roles = []

                # Get all incompatible roles
                for role_data in roles[arguments[2]]["roles"]:
                    # If role is the new role don't add it to list
                    if role_data["id"] == int(arguments[3]):
                        continue
                    print("role found")
                    remove_roles.append(interaction.guild.get_role(role_data["id"]))
                print(*remove_roles)

                for remove in remove_roles:
                    if remove in interaction.user.roles:
                        await interaction.user.remove_roles(remove)

            await interaction.user.add_roles(role)
            await interaction.response.send_message(embed=simple_message_embed(user=interaction.user, message=f":white_check_mark: Added the \"{role.name}\" role to your roles"), ephemeral=True)
            return

    # If the interaction is a command, just process it
    await bot.process_application_commands(interaction)


#@bot.slash_command()
#async def send_roles_message(ctx: discord.ApplicationContext):
#
#    await ctx.defer(ephemeral=True)
#
#    for category in ["colors", "announcements"]:
#        embed = simple_embed(title=roles[category]["label"])
#
#        select_mode = roles[category]["select_mode"]
#
#        buttons = []
#
#        for role in roles[category]["roles"]:
#            buttons.append(discord.ui.Button(label=role["label"], custom_id=f"roles,{select_mode},{category},{role['id']}", style=discord.ButtonStyle.primary))
#
#        await ctx.channel.send(embed=embed, view=discord.ui.View(*buttons))


@bot.slash_command()
async def battle_of_wits(ctx: discord.ApplicationContext, counter_link: str):

    try:

        channel = bot.get_channel(int(counter_link.split("/")[-2]))

        counter = await channel.fetch_message(int(counter_link.split("/")[-1]))
    except:
        await ctx.respond(embed=error_embed(ctx.author, "Invalid message"), ephemeral=True)
        return

    if not counter.reference:
        await ctx.respond(embed=error_embed(ctx.author, "Message has to be a reply to another message"), ephemeral=True)
        return

    await ctx.defer()

    original = await channel.fetch_message(counter.reference.message_id)

    clip = VideoFileClip("data/media/battleOfWits.mp4")

    if original.reference:
        original_reference = await channel.fetch_message(original.reference.message_id)
        img1 = await generate_discord_screenshot(original, 600, 250, original_reference)
    else:
        img1 = await generate_discord_screenshot(original, 600, 250)
    img2 = await generate_discord_screenshot(counter, 600, 250, original)

    image1 = ImageClip(numpy.asarray(img1)).set_start(5.1).set_duration(1.15).set_pos(("center", "center"))
    image2 = ImageClip(numpy.asarray(img2)).set_start(7.8).set_duration(1).set_pos(("center", "center"))

    final = CompositeVideoClip([clip, image1, image2])
    final.write_videofile("data/temporary/bow.mp4")
    clip.close()

    file = discord.File("data/temporary/bow.mp4", filename="battleOfWits.mp4")

    await ctx.respond(file=file)


@bot.slash_command(description="Ask the 8ball a question")
async def eightball(ctx: discord.ApplicationContext, question: str):

    embed = simple_message_embed(ctx.author, f"\🎱 | {question[:200]}")
    embed.description = random.choice(Default.EIGHTBALL_RESPONSES)
    embed.color = Default.BLACK

    await ctx.respond(embed=embed)


bot.run(os.getenv("GENERAL_TOKEN"))
