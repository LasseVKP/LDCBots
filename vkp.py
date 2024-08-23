import discord, pymongo, os, json, random, time, math, io
from dotenv import load_dotenv
from datetime import datetime
from PIL import ImageFont, Image, ImageDraw

load_dotenv()


# Bot classes
class BasicBot(discord.Bot):
    async def on_ready(self):
        print(f"Logged in as {self.user}")


# Database classes


class BaseDatabaseHandler:
    def __init__(self):
        db_client = pymongo.MongoClient(get_env_var("DATABASE_URL"))

        # Initialize the database
        self.db = db_client[get_env_var("DATABASE_NAME")]

    def get_one_value(self, collection: str, query, field: str, fallback):
        content = self.db[collection].find_one(query) or {}
        return content[field] if field in content else fallback

    def get_values(self, collection: str, query):
        return self.db[collection].find(query)

    def get_values_sorted(self, collection: str, query, fields, sort_field: str, sort_direction: int, limit: int = -1):
        return self.db[collection].find(query, fields).sort(sort_field, sort_direction).limit(limit)


class EconomyDatabaseHandler(BaseDatabaseHandler):
    def __init__(self):
        super().__init__()

        # Initialize the collections
        self.econ_col = self.db["economy"]
        self.pets_col = self.db["pets"]

    # Get user balance
    def get_balance(self, user: discord.Member):
        return self.get_one_value(collection="economy", query={"_id": user.id}, field="balance", fallback=0.0)

    def get_pet(self, user: discord.Member):
        return self.get_one_value(collection="pets", query={"_id": user.id}, field="pet", fallback=None)

    def add_pet_xp(self, user: discord.Member, amount: float):
        self.pets_col.update_one({"_id": user.id}, {"$inc": {"pet.xp": round(amount, 1)}})

    def feed_pet(self, user: discord.Member):
        self.pets_col.update_one({"_id": user.id}, {"$set": {"pet.lastFed": get_minute()}})

    def use_pet_big_action(self, user: discord.Member):
        self.pets_col.update_one({"_id": user.id}, {"$set": {"pet.lastBigAction": get_minute()}})

    def replace_pet(self, index):
        self.pets_col.update_one({"_id": -1}, {"$set": {f"pets.{index}": generate_pet()}})

    def rename_pet(self, user: discord.Member, name: str):
        self.pets_col.update_one({"_id": user.id}, {"$set": {"pet.name": name}})

    def get_pets(self):
        last_pet_update = self.get_one_value(collection="pets", query={"_id": -1}, field="lastPetUpdate", fallback=0)
        pets = self.get_one_value(collection="pets", query={"_id": -1}, field="pets", fallback=[])

        if last_pet_update < get_day() or len(pets) == 0:
            if len(pets) == 0:
                self.pets_col.insert_one({"_id": -1, "lastPetUpdate": 0, "pets": []})
            pets = []

            for x in range(6):
                pets.append(generate_pet())

            self.pets_col.find_one_and_update({"_id": -1}, {"$set": {"pets": pets, "lastPetUpdate": get_day()}})

        return pets

    def set_pet(self, user: discord.Member, pet):
        self.pets_col.insert_one({"_id": user.id, "pet": convert_pet(pet)})

    def remove_pet(self, user: discord.Member):
        self.pets_col.delete_one({"_id": user.id})

    def get_token_pool(self):
        return self.get_one_value(collection="economy", query={"_id": -1}, field="pool", fallback=0)

    def get_tokens(self, user: discord.Member):
        return self.get_one_value(collection="economy", query={"_id": user.id}, field="tokens", fallback=0)

    def get_tokens_bought(self, user: discord.Member):
        return self.get_one_value(collection="economy", query={"_id": user.id}, field="tokens_bought", fallback=0)

    def get_token_leaderboard(self, limit=10):
        return list(self.get_values_sorted(collection="economy", query={"_id": {"$gt": 0}},
                                           fields={"cached_name": 1, "tokens": 1, "_id": 1},
                                           sort_field="tokens", sort_direction=-1, limit=limit))

    def get_leaderboard(self, limit=10):
        return list(self.get_values_sorted(collection="economy", query={"_id": {"$gt": 0}},
                                           fields={"cached_name": 1, "balance": 1, "_id": 1},
                                           sort_field="balance", sort_direction=-1, limit=limit))

    # Add to user balance
    def add_balance(self, user: discord.Member, amount: float):
        user_properties = self.econ_col.find_one({"_id": user.id}) or False

        # Check if user is already created
        if user_properties:
            self.econ_col.find_one_and_update({"_id": user.id},
                                              {"$inc": {"balance": floor(amount, 2)},
                                               "$set": {"cached_name": user.display_name}})
            return floor(user_properties["balance"] + amount, 2)
        else:
            self.econ_col.insert_one({"_id": user.id, "balance": floor(amount, 2),
                                      "cached_name": user.display_name, "tokens": 0, "tokens_bought": 0})
            return floor(amount, 2)

    def add_tokens(self, user: discord.Member, amount: int, buy: bool = False):
        user_properties = self.econ_col.find_one({"_id": user.id}) or False

        # Check if user is already created
        if user_properties:
            update = {"$inc": {"tokens": amount},
                      "$set": {"cached_name": user.display_name}}
            if buy:
                update["$inc"]["tokens_bought"] = amount
            self.econ_col.find_one_and_update({"_id": user.id}, update)
            return user_properties["tokens"] + amount
        else:
            insert = {"_id": user.id, "balance": 0, "cached_name": user.display_name, "tokens": amount}
            if buy:
                insert["tokens_bought"] = amount
            self.econ_col.insert_one(insert)
            return amount

    def add_token_pool(self, amount: int):
        pool = self.econ_col.find_one({"_id": -1}) or False

        # Check if pool is already created
        if pool:
            self.econ_col.find_one_and_update({"_id": -1},
                                              {"$inc": {"pool": amount}})
            return pool["pool"] + amount
        else:
            self.econ_col.insert_one({"_id": -1, "pool": amount, 'dailies': create_dailies(get_day(), 5)})
            return amount

    def reset_tokens(self):
        leaderboard = self.get_token_leaderboard(3)
        if len(leaderboard) == 0:
            self.econ_col.find_one_and_delete({"_id": -1})
            return leaderboard, 0

        pool = self.get_token_pool()

        winner_amount = len(leaderboard)

        winners = []

        for x in range(winner_amount):
            # w = winner_amount, i = index, pool = pool, token_value = Default.TOKEN_VALUE
            # Rewards calculated (w - i) / (w * ((w+1)/2)) * pool * token_value
            reward = floor(
                round(((winner_amount - x) / (winner_amount * ((winner_amount + 1) / 2)) * pool)) * Default.TOKEN_VALUE,
                2)

            user_id = leaderboard[x]["_id"]
            name = leaderboard[x]["cached_name"]

            # Add reward to user using this method because add_balance needs a discord.Member object
            self.econ_col.update_one({"_id": user_id}, {"$inc": {"balance": reward}})

            # Add winner and reward
            winners.append({"_id": user_id, "reward": reward, "name": name})

        # Remove pool and all tokens in circulation
        self.econ_col.update_many({"_id": {"$gt": 0}}, {"$set": {"tokens": 0, "tokens_bought": 0}})
        self.econ_col.update_one({"_id": -1}, {"$set": {"pool": 0}})

        return winners, pool

    def get_dailies(self):
        daily = self.econ_col.find_one({"_id": -1}) or False
        if daily:
            dailies = daily['dailies']

            # If daily hasn't been updated create new days
            if get_day() is not dailies[0]['day']:
                difference = get_day() - dailies[0]['day']
                start = get_day() + (5 - difference)
                if difference >= 5:
                    dailies = create_dailies(get_day(), 5)
                else:
                    dailies = dailies[difference:] + create_dailies(start, difference)
                self.econ_col.update_one({"_id": -1}, {"$set": {'dailies': dailies}})

            return dailies

        dailies = create_dailies(get_day(), 5)

        self.econ_col.insert_one({"_id": -1, 'pool': 0, 'dailies': dailies})

        return dailies

    def is_daily_claimed(self, user: discord.Member):
        econ_user = self.econ_col.find_one({"_id": user.id}) or False
        if not econ_user:
            return False
        if 'daily' not in econ_user:
            return False
        if econ_user['daily'] < get_day():
            return False
        return True

    def claim_daily(self, user: discord.Member):
        econ_user = self.econ_col.find_one({"_id": user.id}) or False
        daily = self.get_dailies()[0]
        self.add_token_pool(daily['tokens'])
        if not econ_user:
            self.econ_col.insert_one({"_id": user.id, "balance": daily['money'],
                                      "cached_name": user.display_name, "tokens": daily['tokens'], "tokens_bought": 0,
                                      'daily': get_day()})
            return daily

        self.econ_col.update_one({"_id": user.id},
                                 {"$set": {'daily': get_day(), "cached_name": user.display_name},
                                  "$inc": {"balance": daily['money'],
                                           "tokens": daily['tokens']}})
        return daily


def create_dailies(start: int, amount: int):
    dailies = []

    for x in range(amount):
        money = floor(random.randint(Default.MIN_DAILY_MONEY, Default.MAX_DAILY_MONEY), -1)
        tokens = int(round(random.randint(Default.MIN_DAILY_TOKENS, Default.MAX_DAILY_TOKENS), -1))
        dailies.append({"money": money, "tokens": tokens, "day": start + x})
    return dailies


def generate_pet():
    pet = {}

    with open("data/templates/petNames.json", "r") as f:
        pet["name"] = random.choice(json.load(f))

    with open("data/templates/petWeights.json", "r") as f:
        pets = json.load(f)
        types = list(pets.keys())
        weights = [pets[key] for key in types]

        pet["type"] = random.choices(types, weights=weights, k=1)[0]

    with open("data/templates/petTemplates.json", "r") as f:
        template = json.load(f)[pet["type"]]

    pet["age"] = random.randint(4, int(template["maxAge"] * 0.75))
    pet["price"] = int(floor(random.randint(template["minPrice"], template["maxPrice"]) * (1-pet["age"]/template["maxAge"]*0.5), -1)) # Price is randint(minPrice, maxPrice) * (1-percent_of_life_lived * 0.5) floored to the nearest 10
    pet["image"] = random.choice(template["images"])
    pet['xp'] = floor(2500 * (pet["age"]/template["maxAge"]) * (pet['price']/template['maxPrice']*2), 1) # Starting xp is 5000 * (percent_of_life_lived * 1) * (percent_of_max_price * 2) floored to 1 decimal point

    return pet


def convert_pet(pet):
    return {"name": pet['name'],
            "type": pet['type'],
            "image": pet['image'],
            "born": get_day()-pet['age'],
            "lastFed": get_minute()-120,
            "xp": pet['xp'],
            "lastBigAction": get_minute()-60}


def calc_pet_level(xp: float):  # Level is calculated by round(log1.25((xp + 1000) / 1000)) + 1 meaning levels require 250 * 1.25^n-1 xp
    return int(math.log((xp+1000)/1000, 1.25))+1


def calc_next_pet_level_xp(level: int):
    return ceil(sum(250 * 1.25 ** n for n in range(level)), 1)


class Blackjack:
    def __init__(self):
        self.deck = None
        self.load_deck()

    def load_deck(self):
        with open("data/templates/cardDeck.json", "r") as f:
            self.deck = json.load(f)

    class BlackJackView(discord.ui.View):
        def __init__(self, deck: list, user: discord.Member, amount: int, db: EconomyDatabaseHandler):
            super().__init__()
            self.deck = deck
            self.user = user
            self.amount = amount
            self.db = db
            self.title = "♠ Blackjack ♦"
            self.footer = "Dealer must draw to 16 and stand on all 17's"
            self.timestamp = datetime.now()
            self.footer_icon = user.display_avatar.url
            self.user_hand = [self.random_card() for _ in range(2)]
            self.dealer_hand = [self.random_card() for _ in range(2)]
            self.embed = self.check_for_blackjack() or self.current_hand_embed()
            self.timeout = 120
            self.disable_on_timeout = True

        @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
        async def hit_callback(self, _, interaction: discord.Interaction):
            # Check if the user is the correct user
            if interaction.user is not self.user:
                await interaction.response.defer()
                return

            embed = self.user_draw()

            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Stand", style=discord.ButtonStyle.primary)
        async def stand_callback(self, _, interaction: discord.Interaction):
            # Check if the user is the correct user
            if interaction.user is not self.user:
                await interaction.response.defer()
                return

            embed = self.dealer_draw()

            await interaction.response.edit_message(embed=embed, view=self)

        # Check for dealer or user blackjack
        def check_for_blackjack(self):
            if self.calculate_hand(self.user_hand) == 21:
                if self.calculate_hand(self.dealer_hand) == 21:  # Draw
                    return self.game_draw()
                return self.user_win("Blackjack!", floor(self.amount * 1.5, 2))  # User Blackjack
            if self.calculate_hand(self.dealer_hand) == 21:  # Dealer blackjack
                return self.dealer_win("Dealer got blackjack!")

        # User draws card
        def user_draw(self):
            self.user_hand.append(self.random_card())
            if self.calculate_hand(self.user_hand) > 21:  # User bust
                return self.dealer_win("Bust!")
            if self.calculate_hand(self.user_hand) == 21:  # Time for dealer to draw
                return self.dealer_draw()

            return self.current_hand_embed()  # Nothing happens

        # Dealer draws cards
        def dealer_draw(self):
            while self.calculate_hand(self.dealer_hand) < 17:
                self.dealer_hand.append(self.random_card())

            dealer_value = self.calculate_hand(self.dealer_hand)
            user_value = self.calculate_hand(self.user_hand)

            if dealer_value > 21:  # Dealer bust
                return self.user_win("Dealer bust!", self.amount)
            if dealer_value == user_value:  # Draw
                return self.game_draw()
            if dealer_value > user_value:  # Dealer win
                return self.dealer_win("Dealer won!")

            return self.user_win("You won!", self.amount)  # User win

        def dealer_win(self, reason: str):
            embed = self.current_hand_embed(True)
            embed.add_field(name=reason,
                            value=f"You lost {format_tokens(self.amount)}")

            self.disable_all_items()
            self.stop()
            return embed

        def user_win(self, reason: str, amount: int):
            embed = self.current_hand_embed(True)
            embed.add_field(name=reason,
                            value=f"You won {format_tokens(amount)}")

            self.db.add_tokens(self.user, self.amount + amount)

            self.disable_all_items()
            self.stop()
            return embed

        def game_draw(self):
            embed = self.current_hand_embed(True)
            embed.add_field(name="Draw!",
                            value="You get your tokens back!")

            self.db.add_tokens(self.user, self.amount)

            self.disable_all_items()
            self.stop()
            return embed

        # Get a random card and remove it from the deck
        def random_card(self):
            card = random.choice(self.deck)
            self.deck.remove(card)
            return card

        def calculate_hand(self, hand):
            total_value = 0
            ace_count = 0

            # Add all card values, and assume ace is 11
            for card in hand:
                value = card["value"]
                if value == "ace":
                    ace_count += 1
                    total_value += 11
                else:
                    total_value += value

            # Adjust value of aces
            while ace_count > 0 and total_value > 21:
                total_value -= 10
                ace_count -= 1

            return total_value

        def current_hand_embed(self, win: bool = False):
            return simple_embed(title="♠ Blackjack ♦", fields=self.hand_embed_fields(win),
                                footer=self.footer, timestamp=self.timestamp,
                                footer_icon=self.footer_icon)

        def hand_embed_fields(self, win: bool = False):

            # Hide one card if game isn't won yet
            dealer_hand = self.dealer_hand if win else [self.dealer_hand[0], {"card": "<:cardBack:941039219135086622>",
                                                                              "value": 0}]

            dealer_cards = "".join([card["card"] for card in dealer_hand])
            dealer_value = self.calculate_hand(dealer_hand)

            user_cards = "".join([card["card"] for card in self.user_hand])
            user_value = self.calculate_hand(self.user_hand)

            return [
                {"name": f"Dealer | {dealer_value}",
                 "value": dealer_cards},
                {"name": f"User | {user_value}",
                 "value": user_cards}
            ]

    def create_view(self, user: discord.Member, amount: int, db: EconomyDatabaseHandler):
        return self.BlackJackView(self.deck.copy(), user, amount, db)


class DailyView(discord.ui.View):
    def __init__(self, member: discord.Member, edb: EconomyDatabaseHandler):
        super().__init__()
        self.member = member
        self.edb = edb
        self.timeout = 60
        self.disable_on_timeout = True

    @discord.ui.button(label="Claim daily", style=discord.ButtonStyle.primary)
    async def claim_daily(self, _, interaction: discord.Interaction):
        # Check if the user is the correct user
        if interaction.user is not self.member:
            await interaction.response.defer()
            return
        await self.disable()
        if self.edb.is_daily_claimed(self.member):
            await interaction.response.send_message(
                embed=error_embed(self.member, "You have already claimed today's daily reward"), ephemeral=True)
            return
        daily = self.edb.claim_daily(self.member)
        embed = simple_message_embed(self.member,
                                     f"You claimed today's daily of {format_money(daily['money'])} and {format_tokens(daily['tokens'])}")
        embed.description = f"{format_tokens(daily['tokens'])} were added to the token pool"
        await interaction.response.send_message(embed=embed)

    async def disable(self):
        self.disable_all_items()
        self.stop()
        await self.message.edit(view=self)


# Default values
class Default:
    # Constants
    COLOUR = 0x3044ff
    ERROR_COLOUR = 0xFF3030
    SUCCESS_COLOUR = 0x30FF33
    EMBED_COLOUR = 0x202225
    EMBED_BACKGROUND_COLOUR = 0x2f3136
    BLACK = 0x000000
    TOKEN_VALUE = 0.01
    MAX_WEEKLY_TOKENS = 50000
    MAX_DAILY_MONEY = 250
    MIN_DAILY_MONEY = 100
    MAX_DAILY_TOKENS = 5000
    MIN_DAILY_TOKENS = 1000
    GUILD = os.getenv("GUILD")
    ANNOUNCEMENTS_CHANNEL = os.getenv("BOT_ANNOUNCEMENT_CHANNEL")
    CURRENCY = os.getenv("CURRENCY")
    TOKENS = os.getenv("TOKENS")
    with open("data/templates/diceSides.json", "r") as f:
        DICE_IMAGES = json.load(f)
    with open("data/templates/eightballResponses.json", "r", encoding="utf-8") as f:
        EIGHTBALL_RESPONSES = json.load(f)


# Simple error embed to improve consistency
def error_embed(user: discord.Member, error: str):
    embed = simple_embed(title=error, colour=Default.ERROR_COLOUR,
                         footer_icon=user.display_avatar.url, footer=user.display_name,
                         timestamp=datetime.now())
    return embed


# Simple one line message embed to improve consistency
def simple_message_embed(user: discord.Member, message: str):
    embed = simple_embed(title=message,
                         footer_icon=user.display_avatar.url, footer=user.display_name,
                         timestamp=datetime.now())
    return embed


def simple_embed(title=None, description=None, colour=Default.COLOUR, url=None, fields=None,
                 author_name=None, author_url=None, author_icon=None,
                 footer=None, footer_icon=None,
                 thumbnail=None, image=None, timestamp=None):
    # Change fields into embed fields
    if fields is None:
        fields = []
    embed_fields = []
    for field in fields:
        if "inline" not in field:
            field["inline"] = False
        embed_fields.append(discord.EmbedField(field['name'], field['value'], field['inline']))

    embed = discord.Embed(colour=colour, url=url, fields=embed_fields, timestamp=timestamp)

    if title:
        embed.title = title

    if description:
        embed.description = description

    if not title and not description:
        embed.description = "_ _"

    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon, url=author_url)

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    if image:
        embed.set_image(url=image)

    embed.set_footer(text=footer, icon_url=footer_icon)

    return embed


# Round to floor with n amount of decimal places    0.02 * 10^2 = 2 / 10^2 = 0.02
def floor(i, n):
    return round(int(i * 10 ** n) / 10 ** n, n)


# Round to ceil with n amount of decimal places    0.02 * 10^2 = 2 / 10^2 = 0.02
def ceil(i, n):
    return round(math.ceil(i * 10 ** n) / 10 ** n, n)


# Might delete later
def get_env_var(key: str):
    return os.getenv(key)


# Format money for consistency
def format_money(amount: float):
    amount = floor(amount, 2)
    if int(amount) == amount and amount >= 1000:
        return str(int(amount)) + " " + Default.CURRENCY

    decimals_missing = 2 - count_decimals(amount)

    if decimals_missing == 2:
        return str(amount) + "." + "0" * decimals_missing + " " + Default.CURRENCY
    return str(amount) + "0" * decimals_missing + " " + Default.CURRENCY


# Format tokens for consistency
def format_tokens(amount: int):
    return str(round(amount)) + " " + Default.TOKENS


# Count decimals in a float
def count_decimals(num: float):
    if '.' in str(num):
        return len(str(num).split('.')[1])
    else:
        return 0


# Get current day
def get_day():
    return math.floor((time.time() / 60 / 60 + 1) / 24)


# Get current hour
def get_hour():
    return math.floor(time.time() / 60 / 60 + 1)


# Get current hour
def get_minute():
    return math.floor(time.time() / 60)


async def generate_discord_screenshot(message: discord.Message, width: int, max_height: int, reference: discord.Message = None):
    discord_font = ImageFont.truetype('data/fonts/whitneymedium.otf', 26)
    discord_name_font = ImageFont.truetype('data/fonts/whitneysemibold.otf', 26)
    discord_time_font = ImageFont.truetype('data/fonts/whitneymedium.otf', 16)

    img = Image.new(mode="RGB", size=(width, max_height), color="#313338")

    avatar = Image.open(io.BytesIO(await message.author.display_avatar.read())).resize((60, 60))

    avatar_mask = Image.new("L", avatar.size, 0)
    mask_draw = ImageDraw.Draw(avatar_mask)
    mask_draw.ellipse((0, 0, 60, 60), fill=255)

    img.paste(avatar, (10, 10), mask=avatar_mask)

    draw = ImageDraw.Draw(img)

    draw.text((90, 10), message.author.display_name, font=discord_name_font, fill=(242, 243, 245))

    name_bbox = discord_font.getbbox(message.author.display_name)
    name_length = name_bbox[2] - name_bbox[0]

    draw.text((name_length+100, 20), message.created_at.strftime('%d/%m/%Y %H:%M'), font=discord_time_font, fill=(135, 155, 154))

    lines = text_wrap(message.content, width-100, discord_font)
    start_height = 40
    for line in lines:
        bbox = discord_font.getbbox(line)
        line_height = bbox[3] - bbox[1]
        draw.text((90, start_height), line, font=discord_font, fill=(219, 222, 225))
        start_height += line_height + 10

    img = img.crop((0, 0, img.size[0], min(img.size[1], start_height + 10)))

    if reference:
        reference_img = Image.new(mode="RGB", size=(width, img.size[1]+50), color="#313338")
        reference_img.paste(img, (0, 50))
        reply_symbol = Image.open("data/assets/reply.png")
        reference_img.paste(reply_symbol, (-5, 17))

        avatar = Image.open(io.BytesIO(await reference.author.display_avatar.read())).resize((30, 30))

        avatar_mask = Image.new("L", avatar.size, 0)
        mask_draw = ImageDraw.Draw(avatar_mask)
        mask_draw.ellipse((0, 0, 30, 30), fill=255)

        reference_img.paste(avatar, (115, 12), mask=avatar_mask)

        discord_reply_name_font = ImageFont.truetype('data/fonts/whitneysemibold.otf', 20)
        discord_reply_content_font = ImageFont.truetype('data/fonts/whitneymedium.otf', 20)

        draw = ImageDraw.Draw(reference_img)

        draw.text((150, 14), reference.author.display_name, fill=(166, 168, 170), font=discord_reply_name_font)

        name_bbox = discord_reply_name_font.getbbox(reference.author.display_name)
        name_length = name_bbox[2] - name_bbox[0]

        draw.text((name_length+158, 14), reference.content, fill=(181, 186, 193), font=discord_reply_content_font)

        return reference_img
    else:
        return img


def text_wrap(text: str, max_width: int, font: ImageFont.ImageFont):
    lines = []

    words = text.split(" ")

    amount = 0
    while len(words) > 0:
        amount += 1
        line = " ".join(words[0:amount])
        bbox = font.getbbox(line)
        if bbox[2]-bbox[0] > max_width:
            if amount == 1:
                short_lines = []
                length = 0
                while len(line) > 0:
                    length += 1
                    short_line = line[0:length]
                    bbox = font.getbbox(short_line)
                    if bbox[2] - bbox[0] > max_width:
                        if length == 1:
                            length = 2
                        short_lines.append(line[0:length - 1])
                        line = line[length - 1:]
                        length = 0
                    elif length > len(line):
                        short_lines.append(line)
                        line = []
                lines.extend(short_lines)
                words = words[amount:]
                amount = 0
            else:
                lines.append(" ".join(words[0:amount-1]))
                words = words[amount-1:]
                amount = 0
        elif amount > len(words):
            lines.append(" ".join(words))
            words = []

    return lines

