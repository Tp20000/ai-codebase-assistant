from user import User

class Order:
    def __init__(self, user_id: int, items: list[str]):
        self.user_id = user_id
        self.items = items
        self.status = "pending"

    def add_item(self, item: str):
        self.items.append(item)

    def complete(self):
        self.status = "completed"