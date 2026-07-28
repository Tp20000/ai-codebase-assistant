from helpers import validate_email

class User:
    def __init__(self, name: str, email: str):
        self.id = hash(email)
        self.name = name
        self.email = email

        if not validate_email(email):
            raise ValueError("Invalid email")