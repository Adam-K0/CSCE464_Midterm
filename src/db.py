"""
Provides a simple connection function to MySQL.
"""

import mysql.connector

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,          # XAMPP MySQL port
    "user": "root",
    "password": "",
    "database": "congress_debate",
    "charset": "utf8mb4",
}


def get_conn():
    """Return a new MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)
