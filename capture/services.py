from google.cloud.firestore import SERVER_TIMESTAMP
from config.firebase_config import get_db, get_bucket
from string import ascii_letters, digits
import os


def create_textile_id(title: str) -> str:
    allowed = ascii_letters + digits + "-"
    title = title.strip().lower().replace(" ", "-")

    cleaned_title = ""

    for char in title:
        if char in allowed:
            cleaned_title += char
        else:
            cleaned_title += "-"

    cleaned_title = cleaned_title.strip("-")

    if not cleaned_title:
        raise ValueError("Invalid textile title.")
    
    return cleaned_title

def create_textile(title: str) -> str:
    db = get_db()
    textile_id = create_textile_id(title)
    ref = db.collection("textile").document(textile_id)

    if ref.get().exists:
        raise ValueError("Textile title already exists.")

    ref.set({
        "title": title,
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    })

    return textile_id

def upload_to_storage(textile_id:str, folder: str, file_obj, file_name: str) -> str:
    bucket = get_bucket()

    storage_path = f"teletex/{textile_id}/{folder}/{file_name}"

    blob = bucket.blob(storage_path)

    blob.upload_from_file(
        file_obj.file, content_type=getattr(file_obj, "content_type", None) or "application/octet-stream",
    )

    return storage_path

def add_textile_image_doc(textile_id: str, storage_path: str, file_name) -> str:
    db = get_db()

    doc_ref = (
        db.collection("textile").document(textile_id).collection("textile_image").document(file_name)
    )

    doc_ref.set({
        "name": file_name,
        "storagePath": storage_path,
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    })

    return doc_ref.id

def add_vtimage_doc(textile_id: str, index:int,  storage_path: str, file_name) -> str:
    db = get_db()

    doc_ref = (
        db.collection("textile").document(textile_id).collection("vt_image").document(file_name)
    )

    doc_ref.set({
        "name": file_name,
        "index": index,
        "storagePath": storage_path,
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    })
    return doc_ref.id