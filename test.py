import dotenv
import os


#os.environ["KITCHENHELPER_DB_PATH"] = ".local/orders.db"
if os.environ.get("KITCHENHELPER_DB_PATH") is not None:
    print(os.environ.get("KITCHENHELPER_DB_PATH"))
print(os.environ)
print("hi")