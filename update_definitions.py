#!/usr/bin/env python3
"""Load concept definitions from JSON and update SQLite database."""
import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baoke_learning.db')
JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'concept_defs.json')

# Load definitions
with open(JSON_PATH, 'r', encoding='utf-8') as f:
    definitions = json.load(f)

# Update database
conn = sqlite3.connect(DB_PATH)
updated = 0
for cid_str, definition in definitions.items():
    conn.execute('UPDATE concepts SET definition = ? WHERE id = ?', 
                 (definition, int(cid_str)))
    updated += 1
conn.commit()

# Verify
remaining = conn.execute(
    "SELECT COUNT(*) FROM concepts WHERE definition IS NULL OR definition = ''"
).fetchone()[0]

# Show sample
samples = conn.execute(
    "SELECT id, name, definition FROM concepts WHERE id IN (1, 15, 38, 62) ORDER BY id"
).fetchall()

conn.close()

print(f'Updated: {updated} concepts')
print(f'Remaining empty: {remaining}')
print()
print('Sample outputs:')
for s in samples:
    def_preview = s[2][:80] + '...' if s[2] and len(s[2]) > 80 else s[2]
    print(f'  [{s[0]}] {s[1]}: {def_preview}')
