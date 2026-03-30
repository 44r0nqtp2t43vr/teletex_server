from google.cloud.firestore import SERVER_TIMESTAMP
from config.firebase_config import get_db, get_bucket


def get_textile_blob(textile_id: str):
    bucket = get_bucket()
    prefix = f"teletex/{textile_id}/textile_image/"

    blobs = list(bucket.list_blobs(prefix=prefix))
    print("Found textile blobs:", [b.name for b in blobs])

    image_blobs = []

    for blob in blobs:
        name = blob.name.lower()
        if name.endswith("/"):
            continue

        if name.endswith(".jpg") or name.endswith(".jpeg") or name.endswith(".png"):
            image_blobs.append(blob)

    if len(image_blobs) == 0:
        raise ValueError("Missing textile image.")

    return image_blobs[0]


def get_vt_blobs(textile_id: str):
    bucket = get_bucket()
    prefix = f"teletex/{textile_id}/vt_image/"

    blobs = list(bucket.list_blobs(prefix=prefix))
    vt_files = []

    for blob in blobs:
        name = blob.name.split("/")[-1]
        if not name:
            continue

        lower_name = name.lower()
        if not (
            lower_name.endswith(".jpg")
            or lower_name.endswith(".jpeg")
            or lower_name.endswith(".png")
        ):
            continue

        number_part = name.split("_")[-1].split(".")[0]
        index = int(number_part)

        vt_files.append((index, blob))

    vt_files.sort(key=lambda x: x[0])

    if len(vt_files) != 16:
        raise ValueError(f"Expected exactly 16 VT images, found {len(vt_files)}.")

    return [blob for _, blob in vt_files]


def verify_storage_files(textile_id: str):
    get_textile_blob(textile_id)
    get_vt_blobs(textile_id)


def write_metadata(textile_id: str, title: str):
    textile_blob = get_textile_blob(textile_id)

    update_textile_main_doc(
        textile_id=textile_id,
        title=title,
        textilePath=textile_blob.name
    )

    vt_blobs = get_vt_blobs(textile_id)

    for i, blob in enumerate(vt_blobs, start=1):
        file_name = blob.name.split("/")[-1]
        add_vtimage_doc(textile_id, i, blob.name, file_name)


def add_vtimage_doc(textile_id: str, index: int, storage_path: str, file_name: str) -> str:
    db = get_db()

    doc_ref = (
        db.collection("textile")
        .document(textile_id)
        .collection("vt_image")
        .document(file_name)
    )

    doc_ref.set({
        "name": file_name,
        "index": index,
        "storagePath": storage_path,
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    })

    return doc_ref.id


def update_textile_main_doc(textile_id: str, **fields):
    db = get_db()
    ref = db.collection("textile").document(textile_id)

    data = {
        "updated_at": SERVER_TIMESTAMP,
    }

    for key, value in fields.items():
        if value is not None:
            data[key] = value

    if not ref.get().exists:
        data["created_at"] = SERVER_TIMESTAMP

    ref.set(data, merge=True)