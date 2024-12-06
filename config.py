import os
from dotenv import load_dotenv


load_dotenv()  # Carga las variables del archivo .env

""" Bot Configuration """

class DefaultConfig:

    """ Bot Configuration """

    PORT = 3979
    APP_ID = os.environ.get("MicrosoftAppId")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword")
    COSMOS_DB_URI=os.environ.get("COSMOS_DB_URI")
    COSMOS_DB_PRIMARY_KEY=os.environ.get("COSMOS_DB_PRIMARY_KEY")
    COSMOS_DB_DATABASE_ID=os.environ.get("COSMOS_DB_DATABASE_ID")
    COSMOS_DB_CONTAINER_ID=os.environ.get("COSMOS_DB_CONTAINER_ID")

