from helpers import format_date, calculate_total
from user import User
from order import Order
from auth import authenticate

def main():
    user = User(name="Alice", email="alice@example.com")
    if authenticate(user):
        order = Order(user_id=user.id, items=["item1", "item2"])
        total = calculate_total(order.items)
        print(f"Order total: {total}")

if __name__ == "__main__":
    main()