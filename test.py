import dotenv
import os


dotenv.load_dotenv("static_condddddfig.env")

if os.environ.get("TEST_ENV") is not None:
    print("test")
print(os.environ)
print("hi")