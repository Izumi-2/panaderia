import sqlite3
conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()
cur.execute('INSERT OR IGNORE INTO panaderia_marca (id, nombre, tipo) VALUES (?, ?, ?)', (1, '(sin marca)', 'recurso'))
conn.commit()
print('marcas now:', list(cur.execute('SELECT id, nombre, tipo FROM panaderia_marca')))
print('items now:', list(cur.execute('SELECT id, marca_id, tipo_item FROM panaderia_panaderia_items')))
conn.close()
