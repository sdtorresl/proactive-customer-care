#!/.venv/bin/python3

from twilio.rest import Client
import os
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
client = Client(account_sid, auth_token)  # client credentials from clients.json

# for i in range(20):
#     try:
#         client.messages.create(
#             to="+1000000000",          # intentionally invalid number
#             from_="+19027064799",      # real Twilio number from that subaccount
#             body=f"test error {i}",
#         )
#     except Exception as e:
#         print("Forced error:", e)

for i in range(30):
    try:
        client.messages.create(
            body="", # Required data is missing (Error 21602)
            from_='+12345678901',
            to='letters_not_a_number' # Invalid format
        )
    except Exception as e:
        print("Forced error:", e)