import os
import requests


def firebase_signup(email: str, password: str) -> dict:
    api_key = os.getenv("FIREBASE_API_KEY")
    if not api_key:
        raise RuntimeError("FIREBASE_API_KEY not set")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={api_key}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        data = response.json()
        message = data.get("error", {}).get("message", "Firebase signup failed")
        raise ValueError(message)
    return response.json()


def firebase_signin(email: str, password: str) -> dict:
    api_key = os.getenv("FIREBASE_API_KEY")
    if not api_key:
        raise RuntimeError("FIREBASE_API_KEY not set")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        data = response.json()
        message = data.get("error", {}).get("message", "Firebase signin failed")
        raise ValueError(message)
    return response.json()


def firebase_google_signin(id_token: str) -> dict:
    """Sign in to Firebase using a Google ID token."""
    api_key = os.getenv("FIREBASE_API_KEY")
    if not api_key:
        raise RuntimeError("FIREBASE_API_KEY not set")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={api_key}"
    payload = {
        "postBody": f"id_token={id_token}&providerId=google.com",
        "requestUri": "http://localhost",
        "returnSecureToken": True,
        "returnIdpCredential": True,
    }
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        data = response.json()
        message = data.get("error", {}).get("message", "Firebase Google signin failed")
        raise ValueError(message)
    return response.json()
