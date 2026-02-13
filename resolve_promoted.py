import requests
import sqlite3

DB_PATH = "data/db.sqlite3"

def resolve_id(entity_type, entity_id):
    url = f"https://api.openalex.org/{entity_type}/{entity_id}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json().get('display_name')
    except:
        pass
    return "Unknown"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("PROMOTED JOURNALS:")
cursor.execute("SELECT source_id FROM monitored_journals")
for (sid,) in cursor.fetchall():
    name = resolve_id("sources", sid)
    print(f"- {name} ({sid})")

print("\nPROMOTED AUTHORS:")
cursor.execute("SELECT author_id FROM monitored_authors")
for (aid,) in cursor.fetchall():
    name = resolve_id("authors", aid)
    print(f"- {name} ({aid})")

conn.close()
