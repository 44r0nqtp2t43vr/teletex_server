import firebase_admin
from firebase_admin import credentials, firestore, storage
from django.conf import settings

firebase_app = None

def initialize_firebase():
    global firebase_app
    if firebase_app is None:
        cred = credentials.Certificate(settings.FIREBASE_CRED_PATH)
        firebase_app = firebase_admin.initialize_app(cred, {
            "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
        })

def get_db():
    initialize_firebase()
    return firestore.client()

def get_bucket():
    initialize_firebase()
    return storage.bucket()
