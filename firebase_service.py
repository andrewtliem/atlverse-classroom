import os
import json
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

class FirebaseService:
    def __init__(self):
        self.app = None
        self.initialize_firebase()
    
    def initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Get the service account key from environment
            service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY')
            if not service_account_json or service_account_json.strip() == '':
                print("FIREBASE_SERVICE_ACCOUNT_KEY not found - Firebase authentication will be disabled")
                self.app = None
                return
            
            # Parse the JSON string
            service_account_info = json.loads(service_account_json)
            
            # Initialize Firebase Admin SDK
            if not firebase_admin._apps:
                cred = credentials.Certificate(service_account_info)
                self.app = firebase_admin.initialize_app(cred)
            else:
                self.app = firebase_admin.get_app()
                
            print("Firebase Admin SDK initialized successfully")
            
        except Exception as e:
            print(f"Error initializing Firebase: {str(e)}")
            print("Firebase authentication will be disabled - falling back to regular authentication")
            self.app = None
    
    def verify_id_token(self, id_token):
        """Verify Firebase ID token and return user info"""
        if not self.app:
            print("Firebase not initialized - cannot verify token")
            return None
            
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            return decoded_token
        except Exception as e:
            print(f"Error verifying ID token: {str(e)}")
            return None
    
    def get_user_role_from_email(self, email):
        """Determine user role based on email domain"""
        if email.endswith('@unklab.ac.id'):
            return 'teacher'
        else:
            return 'student'

# Global instance
firebase_service = FirebaseService()