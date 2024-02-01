import discord, pymongo, os
from dotenv import load_dotenv

load_dotenv()


class BasicBot(discord.Bot):
    async def on_ready(self):
        print(f"Logged in as {self.user}")


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
    def get_balance(self, user: discord.User):
        user_properties = self.money_col.find_one({"_id": user.id}) or False
        if user_properties:
            return user_properties["balance"]
        else:
            return 0.0

    # Add balance to user
    def add_balance(self, user: discord.User, amount: float):
        user_properties = self.money_col.find_one({"_id": user.id}) or False
        # Check if user is already created
        if user_properties:
            self.money_col.find_one_and_update({"_id": user.id}, {"$set": {"balance": round(user_properties["balance"]+amount, 2)}})
        else:
            self.money_col.insert_one({"_id": user.id, "balance": round(amount, 2)})


def get_env_var(key: str):
    return os.getenv(key)
