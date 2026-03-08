"""
Provides a simple connection function to MySQL.
"""

import mysql.connector

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3307,          # XAMPP default MySQL port
    "user": "root",
    "password": "",
    "database": "eshop_adv",
    "charset": "utf8mb4",
}


def get_conn():
    """Return a new MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)
