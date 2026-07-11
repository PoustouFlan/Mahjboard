# app/db.py
import sqlite3
import click
from flask import current_app, g

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("PRAGMA foreign_keys = ON")
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            
            -- General Rating (All games)
            rating REAL DEFAULT 1500.0,
            games_played INTEGER DEFAULT 0,

            -- 4-Player Specific
            rating_4p REAL DEFAULT 1500.0,
            games_4p INTEGER DEFAULT 0,

            -- 3-Player Specific
            rating_3p REAL DEFAULT 1500.0,
            games_3p INTEGER DEFAULT 0
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            game_type INTEGER DEFAULT 4 
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS results (
            game_id INTEGER,
            player_id INTEGER,
            
            raw_score INTEGER,
            net_score REAL,
            
            -- General Rating Snapshot
            rating_change_general REAL,
            new_rating_general REAL,
            rank_change_general REAL,

            -- Mode Specific Snapshot (3p or 4p)
            rating_change_mode REAL,
            new_rating_mode REAL,
            rank_change_mode REAL,

            FOREIGN KEY(game_id) REFERENCES games(id),
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    ''')
    db.commit()

def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
