import os
import requests

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")

if not FIREBASE_API_KEY:
    raise ValueError("FIREBASE_API_KEY environment variable is required")

SIGN_UP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
SIGN_IN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"


def firebase_signup(email: str, password: str) -> dict:
    payload = {"email": email, "password": password, "returnSecureToken": True}
    response = requests.post(SIGN_UP_URL, json=payload)
    if response.status_code != 200:
        data = response.json()
        message = data.get("error", {}).get("message", "Firebase signup failed")
        raise ValueError(message)
    return response.json()


def firebase_signin(email: str, password: str) -> dict:
    payload = {"email": email, "password": password, "returnSecureToken": True}
    response = requests.post(SIGN_IN_URL, json=payload)
    if response.status_code != 200:
        data = response.json()
        message = data.get("error", {}).get("message", "Firebase signin failed")
        raise ValueError(message)
    return response.json()
