import numpy as np
import cv2
import trimesh
from PIL import Image
from config.firebase_config import get_bucket


def storage_path_to_bgr(path):
    bucket = get_bucket()
    blob = bucket.blob(path)

    image_bytes = blob.download_as_bytes()
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(f"Failed to decode image from storage path: {path}")

    return img


def get_vt_paths(textile_id):
    bucket = get_bucket()
    prefix = f"teletex/{textile_id}/vt_image/"

    blobs = list(bucket.list_blobs(prefix=prefix))
    vt_files = []

    for blob in blobs:
        name = blob.name.split("/")[-1]

        if not name:
            continue

        lower = name.lower()
        if not (lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png")):
            continue

        number_part = name.split("_")[-1].split(".")[0]
        index = int(number_part)
        vt_files.append((index, blob.name))

    vt_files.sort(key=lambda x: x[0])

    if len(vt_files) != 16:
        raise ValueError(f"Expected 16 VT images, found {len(vt_files)}.")

    return [path for _, path in vt_files]


def get_textile_path(textile_id):
    bucket = get_bucket()
    prefix = f"teletex/{textile_id}/textile_image/"

    blobs = list(bucket.list_blobs(prefix=prefix))
    image_paths = []

    for blob in blobs:
        name = blob.name.lower()

        if name.endswith("/"):
            continue

        if name.endswith(".jpg") or name.endswith(".jpeg") or name.endswith(".png"):
            image_paths.append(blob.name)

    if len(image_paths) == 0:
        raise ValueError("No textile image found.")

    return image_paths[0]


X_START, Y_START, SIDE_LENGTH = 275, 275, 1371


def create_master_grid_bgr(img_list, size=(500, 500)):
    if len(img_list) != 16:
        raise ValueError(f"Expected 16 images for stitching, got {len(img_list)}.")

    prepared = [cv2.resize(img, size) for img in img_list]
    rows = [np.hstack(prepared[idx:idx + 4]) for idx in range(0, 16, 4)]
    return np.vstack(rows)


def build_binary_from_vtimages(vt_bgr_list, x_start, y_start, side_length):
    RED_WEIGHT, GREEN_WEIGHT, BLUE_WEIGHT = 1.0, 1.6, 1.0
    GAMMA = 0.8
    BILATERAL_D, BILATERAL_SIGMA = 9, 75
    CLAHE_LIMIT = 10
    BLOCK_SIZE, C_VALUE = 99, 1
    MEDIAN_SIZE = 1

    def prep_for_stitch(img, is_gray=False):
        img_res = cv2.resize(img, (500, 500))
        if is_gray or len(img_res.shape) == 2:
            return cv2.cvtColor(img_res, cv2.COLOR_GRAY2RGB)
        return img_res

    def create_master_grid(img_list):
        rows = [np.hstack(img_list[idx:idx + 4]) for idx in range(0, 16, 4)]
        return np.vstack(rows)

    binary_list = []

    for idx, img_bgr in enumerate(vt_bgr_list, start=1):
        if img_bgr is None:
            raise ValueError(f"VT image {idx} could not be decoded.")

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        roi_rgb = img_rgb[y_start:y_start + side_length, x_start:x_start + side_length]
        if roi_rgb.size == 0:
            h, w = img_rgb.shape[:2]
            raise ValueError(
                f"ROI crop empty for vtimage {idx}. Image size={w}x{h}. "
                f"Check X_START/Y_START/SIDE_LENGTH."
            )

        roi_f = roi_rgb.astype(np.float32) / 255.0
        weighted_sum = (
            roi_f[:, :, 0] * RED_WEIGHT
            + roi_f[:, :, 1] * GREEN_WEIGHT
            + roi_f[:, :, 2] * BLUE_WEIGHT
        )

        albedo_u8 = cv2.normalize(
            np.power(np.maximum(weighted_sum, 0), GAMMA),
            None,
            0,
            255,
            cv2.NORM_MINMAX
        ).astype(np.uint8)

        denoised = cv2.bilateralFilter(
            albedo_u8,
            BILATERAL_D,
            BILATERAL_SIGMA,
            BILATERAL_SIGMA
        )

        clahe = cv2.createCLAHE(clipLimit=CLAHE_LIMIT, tileGridSize=(10, 10))
        amplified = clahe.apply(denoised)

        binary_raw = cv2.adaptiveThreshold(
            amplified,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            BLOCK_SIZE,
            C_VALUE
        )

        binary_clean = cv2.medianBlur(binary_raw, MEDIAN_SIZE)
        binary_list.append(prep_for_stitch(binary_clean, is_gray=True))

    final_binary_rgb = create_master_grid(binary_list)
    return final_binary_rgb


def generate_tile_glb_bytes(color_bgr: np.ndarray, depth_rgb: np.ndarray, target_size=(512, 512)):
    color_bgr = cv2.resize(color_bgr, target_size, interpolation=cv2.INTER_AREA)
    depth_rgb = cv2.resize(depth_rgb, target_size, interpolation=cv2.INTER_AREA)

    depth_src = cv2.flip(depth_rgb, 0)
    depth_map = depth_src[:, :, 0] if len(depth_src.shape) == 3 else depth_src

    h, w = depth_map.shape
    depth_norm = depth_map.astype(np.float32) / 255.0
    z_top = 30.0 - (depth_norm * 10.0)

    x = np.linspace(0, w - 1, w)
    y = np.linspace(0, h - 1, h)
    xv, yv = np.meshgrid(x, y)

    v_top = np.stack([xv.ravel(), yv.ravel(), z_top.ravel()], axis=1)
    v_bot = np.stack([xv.ravel(), yv.ravel(), np.zeros_like(z_top.ravel())], axis=1)
    all_vertices = np.vstack([v_top, v_bot])

    u = xv.ravel() / (w - 1)
    v = yv.ravel() / (h - 1)
    uvs_top = np.stack([u, v], axis=1)
    uvs_bot = np.full_like(uvs_top, 0.001)
    all_uvs = np.vstack([uvs_top, uvs_bot])

    def create_grid_faces(offset, rows, cols, flip=False):
        faces = []
        for r in range(rows - 1):
            for c in range(cols - 1):
                v1 = r * cols + c + offset
                v2 = r * cols + (c + 1) + offset
                v3 = (r + 1) * cols + c + offset
                v4 = (r + 1) * cols + (c + 1) + offset
                if flip:
                    faces.extend([[v1, v3, v2], [v2, v3, v4]])
                else:
                    faces.extend([[v1, v2, v3], [v2, v4, v3]])
        return np.array(faces)

    f_top = create_grid_faces(0, h, w, flip=False)
    f_bot = create_grid_faces(h * w, h, w, flip=True)

    side_faces = []
    idx_t = np.arange(h * w).reshape(h, w)
    idx_b = idx_t + (h * w)

    for i in range(w - 1):
        side_faces.extend([
            [idx_t[0, i], idx_b[0, i], idx_t[0, i + 1]],
            [idx_b[0, i], idx_b[0, i + 1], idx_t[0, i + 1]],
        ])
        side_faces.extend([
            [idx_t[-1, i], idx_t[-1, i + 1], idx_b[-1, i]],
            [idx_b[-1, i], idx_t[-1, i + 1], idx_b[-1, i + 1]],
        ])

    for j in range(h - 1):
        side_faces.extend([
            [idx_t[j, 0], idx_t[j + 1, 0], idx_b[j, 0]],
            [idx_b[j, 0], idx_t[j + 1, 0], idx_b[j + 1, 0]],
        ])
        side_faces.extend([
            [idx_t[j, -1], idx_b[j, -1], idx_t[j + 1, -1]],
            [idx_b[j, -1], idx_b[j + 1, -1], idx_t[j + 1, -1]],
        ])

    all_faces = np.vstack([f_top, f_bot, np.array(side_faces)])

    rgb_img = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    material = trimesh.visual.texture.SimpleMaterial(image=pil_img)
    visuals = trimesh.visual.TextureVisuals(uv=all_uvs, material=material)

    mesh = trimesh.Trimesh(
        vertices=all_vertices,
        faces=all_faces,
        visual=visuals,
        process=False
    )

    return mesh.export(file_type="glb")


def upload_bgr_image(textile_id: str, image_bgr: np.ndarray, folder: str, filename_suffix: str):
    bucket = get_bucket()

    file_name = f"{textile_id}_{filename_suffix}.png"
    storage_path = f"teletex/{textile_id}/{folder}/{file_name}"

    ok, buf = cv2.imencode(".png", image_bgr)
    if not ok:
        raise ValueError(f"Failed to encode image for folder '{folder}'.")

    blob = bucket.blob(storage_path)
    blob.upload_from_string(buf.tobytes(), content_type="image/png")

    return storage_path


def upload_rgb_image(textile_id: str, image_rgb: np.ndarray, folder: str, filename_suffix: str):
    image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    return upload_bgr_image(textile_id, image_bgr, folder, filename_suffix)


def upload_glb_bytes(textile_id: str, glb_bytes: bytes):
    bucket = get_bucket()

    file_name = f"{textile_id}_3d.glb"
    storage_path = f"teletex/{textile_id}/model/{file_name}"

    blob = bucket.blob(storage_path)
    blob.upload_from_string(glb_bytes, content_type="model/gltf-binary")

    return storage_path


def generate_and_upload_glb(textile_id, progress_callback=None):
    textile_path = get_textile_path(textile_id)

    if progress_callback:
        progress_callback(
            stage="original_ready",
            progress=1,
            textilePath=textile_path
        )

    color_bgr = storage_path_to_bgr(textile_path)

    vt_paths = get_vt_paths(textile_id)
    vt_bgr_list = [storage_path_to_bgr(p) for p in vt_paths]

    # raw stitched VT preview
    stitched_bgr = create_master_grid_bgr(vt_bgr_list, size=(500, 500))
    stitched_path = upload_bgr_image(
        textile_id,
        stitched_bgr,
        "stitched",
        "stitched"
    )

    if progress_callback:
        progress_callback(
            stage="stitched_ready",
            progress=2,
            stitched_path=stitched_path
        )

    # stitched binary/depth image
    depth_rgb = build_binary_from_vtimages(
        vt_bgr_list,
        X_START,
        Y_START,
        SIDE_LENGTH
    )

    binary_path = upload_rgb_image(
        textile_id,
        depth_rgb,
        "binary",
        "binary"
    )

    if progress_callback:
        progress_callback(
            stage="binary_ready",
            progress=3,
            binary_path=binary_path
        )

    glb_bytes = generate_tile_glb_bytes(color_bgr, depth_rgb)
    glb_path = upload_glb_bytes(textile_id, glb_bytes)

    if progress_callback:
        progress_callback(
            stage="model_ready",
            progress=4,
            glb_path=glb_path
        )

    return {
        "textile_path": textile_path,
        "stitched_path": stitched_path,
        "binary_path": binary_path,
        "glb_path": glb_path,
    }