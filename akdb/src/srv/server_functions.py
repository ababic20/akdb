import socket
import paramiko
import threading
import sys
import json
import configparser
import sqlite3
import hashlib

# Povezivanje s bazom podataka
connection = sqlite3.connect("test.db")
cursor = connection.cursor()

cursor.execute("PRAGMA table_info(example)")
columns = cursor.fetchall()

#for column in columns:
 #   print(column[1])  # Ispisuje ime svakog stupca


cursor.execute("CREATE TABLE IF NOT EXISTS example (id INTEGER, usr TEXT, pas_hash TEXT)")  

cursor.execute("INSERT INTO example VALUES (1, 'testingUser', ?)", (hashlib.sha256("testingPass".encode()).hexdigest(),))
cursor.execute("INSERT INTO example VALUES (2, 'user', ?)", (hashlib.sha256("pass".encode()).hexdigest(),))

cursor.execute("SELECT * FROM example")
rows = cursor.fetchall()

#for row in rows:
 #  print(row)

# Potvrda promjena i zatvaranje veze s bazom podataka
connection.commit()
connection.close()





sys.path.append("../swig/")
import kalashnikovDB as AK47
import sql_executor as sqle

config = configparser.ConfigParser()
config.read('config.ini')
n = int(config["select_options"]["number_of_rows_in_packet"])

#Interface to override classic python server support
class ParamikoServer(paramiko.ServerInterface):
    def __init__(self):
        self.event = threading.Event()
    #Function that checks if the channel can be opened for a requesting client
    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    #Function that checks if the clients username and password match
    def check_auth_password(self, username, password):
        #print("Received username:", username)
        #print("Received password:", password)
        
        connection = sqlite3.connect("test.db")
        cursor = connection.cursor()
        cursor.execute("SELECT usr, pas_hash FROM example WHERE usr = ?", (username,))
        user_data = cursor.fetchone()
        print("User data from database:", user_data)
        connection.close()

        if user_data:
            stored_username, stored_password_hash = user_data
            if username == stored_username and hashlib.sha256(password.encode()).hexdigest() == stored_password_hash:
                return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

#Class that handles connection from client to the server
class Connection:
    def __init__(self, conn, addr):
        try:
            self.addr = addr
            self.transport = paramiko.Transport(conn)
            self.transport.add_server_key(paramiko.RSAKey.generate(2048))
            self.transport.start_server(server=ParamikoServer())
            self.channel = self.transport.accept(timeout=1)
        except Exception as e:
            self.addr = False
            print("Error initializing connection:", e)

    def __del__(self):
        if self.channel is not None:
            self.channel.close()
        if self.transport is not None:
            self.transport.close()

    def send_data(self, data):
        try:
            if data[1].startswith('Error'):
                self.channel.send(self.pack_output({"success": False, "error_msg": data[1]}))
            elif data[1] is False:
                self.channel.send(self.pack_output({"success": False, "error_msg": "There was an error in your command."}))
            elif data[0] == "Select_command":
                self.select_protocol(data[1])
            else:
                self.channel.send(self.pack_output({"success": True, "result": data[1]}))
        except Exception as e:
            print("[-] Failed to send data:", e)

    def recv_data(self):
        try:
            data = self.unpack_input(self.channel.recv(1024))
            if isinstance(data, dict):
                if "command" in data:
                    return data["command"]
                elif "continue" in data:
                    return data["continue"]
            return False
        except Exception as e:
            print("[-] Failed while unpacking data:", e)
            return False

    def pack_output(self, out):
        return json.dumps(out)

    def unpack_input(self, inp):
        return json.loads(inp)

    def select_protocol(self, table):
        if not isinstance(table, str):
            print("Invalid table format")
            return

        l = table.splitlines()
        if not l:
            print("Empty table received")
            return

        if len(l) > n:
            header = [l.pop(0)]
            for i in range(0, len(l), n):
                endrow = min(i + n, len(l))
                data = {
                    "startrow": i,
                    "endrow": endrow,
                    "max": len(l),
                    "end": endrow == len(l),
                    "result": '\n'.join(header + l[i:endrow]),
                    "success": True,
                    "packed_data": True
                }
                self.channel.send(self.pack_output(data))
                print(f"Sent {endrow}/{len(l)} rows to {self.addr[0]}")
                res = self.recv_data()
                if not res:
                    print("Interrupted by client.")
                    break
        else:
            data = {
                "rows": len(l) - 1,
                "result": table,
                "success": True
            }
            self.channel.send(self.pack_output(data))

    def is_alive(self):
        return self.channel is not None and self.transport.is_active()
