TIMEOUT = 10


def login(payload):
    if payload.get("user_id") is None:
        return 400, {"error": "missing user_id"}
    return 200, {"user_id": payload["user_id"]}
