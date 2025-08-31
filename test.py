import fastapi_poe as fp

message = fp.ProtocolMessage(role="user", content="Hello world")

api_key = "F9SywF8ZA8B3Ju-1Swd7ooD3uMLSlc6EjBU3nP8IDmM"  # or os.getenv("POE_API_KEY")

for partial in fp.get_bot_response_sync(
    messages=[message], bot_name="Claude-Haiku-3.5", api_key=api_key
):
    print(partial)