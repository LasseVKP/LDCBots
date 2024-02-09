import discord, pymongo, os, json, random
from dotenv import load_dotenv
from datetime import datetime

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


class EconomyDatabaseHandler(BaseDatabaseHandler):
    def __init__(self):
        super().__init__()

        # Initialize the collections
        self.money_col = self.db["money"]

    # Get user balance
    def get_balance(self, user: discord.Member):
        user_properties = self.money_col.find_one({"_id": user.id}) or False
        if user_properties:
            return user_properties["balance"]
        else:
            return 0.0

    # Add to user balance
    def add_balance(self, user: discord.Member, amount: float):
        user_properties = self.money_col.find_one({"_id": user.id}) or False

        # Check if user is already created
        if user_properties:
            self.money_col.find_one_and_update({"_id": user.id},
                                               {"$set": {"balance": floor(user_properties["balance"] + amount, 2),
                                                                "cached_name": user.display_name}})
            return floor(user_properties["balance"] + amount, 2)
        else:
            self.money_col.insert_one({"_id": user.id, "balance": floor(amount, 2), "cached_name": user.display_name})
            return floor(amount, 2)

    def add_tokens(self, user: discord.Member, amount: int):
        user_properties = self.money_col.find_one({"_id": user.id}) or False

        # Check if user is already created
        if user_properties:
            self.money_col.find_one_and_update({"_id": user.id},
                                               {"$set": {"tokens": user_properties["tokens"] + amount,
                                                         "cached_name": user.display_name}})
            return user_properties["tokens"] + amount
        else:
            self.money_col.insert_one({"_id": user.id, "balance": 0, "cached_name": user.display_name, "tokens": amount})
            return amount

    def get_tokens(self, user: discord.Member):
        user_properties = self.money_col.find_one({"_id": user.id}) or False
        if user_properties:
            return user_properties["tokens"]
        else:
            return 0

    def get_token_leaderboard(self, limit=10):
        users = self.money_col.find({}, {"cached_name": 1, "tokens": 1, "_id": 1}).sort("tokens", -1).limit(limit)
        return list(users)

    def get_leaderboard(self, limit=10):
        users = self.money_col.find({}, {"cached_name": 1, "balance": 1, "_id": 0}).sort("balance", -1).limit(limit)
        return list(users)


class Blackjack:
    def __init__(self):
        self.deck = None
        self.load_deck()

    def load_deck(self):
        with open("templates/cardDeck.json", "r") as f:
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

            self.db.add_balance(self.user, amount * 2)

            self.disable_all_items()
            self.stop()
            return embed

        def game_draw(self):
            embed = self.current_hand_embed(True)
            embed.add_field(name="Draw!",
                            value="You get your money back!")

            self.db.add_balance(self.user, self.amount)

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

        async def on_timeout(self):
            embed = self.dealer_draw()
            await self.message.edit(embed=embed, view=self)

    def create_view(self, user: discord.Member, amount: int, db: EconomyDatabaseHandler):
        return self.BlackJackView(self.deck, user, amount, db)


# Default values
class Default:
    # Constants
    COLOUR = 0x3044ff
    ERROR_COLOUR = 0xFF3030
    SUCCESS_COLOUR = 0x30FF33
    EMBED_COLOUR = 0x202225
    EMBED_BACKGROUND_COLOUR = 0x2f3136
    BLACK = 0x000000


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


# Round to floor with n amount of decimal places
def floor(i, n):
    return round(int(i * 10 ** n) / 10 ** n, n)


# Might delete later
def get_env_var(key: str):
    return os.getenv(key)


# Format money for consistency
def format_money(amount: float):
    return str(amount) + "$"


# Format tokens for consistency
def format_tokens(amount: int):
    return str(amount) + " Tokens"

