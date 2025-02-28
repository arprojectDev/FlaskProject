import os
import urllib.parse

DB_SERVER = "DB"
DB_NAME = "DB"
DB_USER = "DB"
DB_PASSWORD = urllib.parse.quote_plus("DB")

SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}/{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server"
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = os.urandom(24)
