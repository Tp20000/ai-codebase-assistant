from helpers import format_date

class Database:
    def __init__(self, url: str):
        self.url = url
        self.connected = False

    def connect(self):
        self.connected = True
        print(f"Connected at {format_date(__import__('datetime').datetime.now())}")

    def query(self, sql: str) -> list:
        if not self.connected:
            raise RuntimeError("Not connected")
        return []