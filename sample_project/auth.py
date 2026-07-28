from user import User

def authenticate(user: User) -> bool:
    return user.email is not None and len(user.name) > 0

def generate_token(user: User) -> str:
    return f"token_{user.id}_{user.email}"