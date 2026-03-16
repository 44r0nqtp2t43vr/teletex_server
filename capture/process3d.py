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
        raise ValueError("Expected 16 VT images.")

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
# def uploaded_file_to_bgr(file_obj):
#     file_obj.seek(0)  
#     file_bytes = file_obj.read()

#     img_array = np.frombuffer(file_bytes, np.uint8)
#     img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
#     if img is None:
#         raise ValueError("Image error!")
    
#     file_obj.seek(0)  

#     return img

X_START, Y_START, SIDE_LENGTH = 275, 275, 1371

def build_binary_from_vtimages(vt_bgr_list, X_START, Y_START, SIDE_LENGTH):

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
        rows = [np.hstack(img_list[idx:idx+4]) for idx in range(0, 16, 4)]
        return np.vstack(rows)

    binary_list = []

    for idx, img_bgr in enumerate(vt_bgr_list, start=1):

        if img_bgr is None:
            raise ValueError(f"Vtimage could not be decoded.")

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # B. ROI Crop & Albedo
        roi_rgb = img_rgb[Y_START:Y_START + SIDE_LENGTH, X_START:X_START + SIDE_LENGTH]
        print("roi shape:", roi_rgb.shape)
        if roi_rgb.size == 0:
            h, w = img_rgb.shape[:2]
            raise ValueError(
                f"ROI crop empty for vtimage {idx}. Image size={w}x{h}. "
                f"Check X_START/Y_START/SIDE_LENGTH."
            )

  
        roi_f = roi_rgb.astype(np.float32) / 255.0
        weighted_sum = (roi_f[:, :, 0] * RED_WEIGHT +roi_f[:, :, 1] * GREEN_WEIGHT +roi_f[:, :, 2] * BLUE_WEIGHT)
        albedo_u8 = cv2.normalize(np.power(np.maximum(weighted_sum, 0), GAMMA),None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # C. Denoising & Amplification
        denoised = cv2.bilateralFilter(albedo_u8, BILATERAL_D, BILATERAL_SIGMA, BILATERAL_SIGMA)
        clahe = cv2.createCLAHE(clipLimit=CLAHE_LIMIT, tileGridSize=(10, 10))
        amplified = clahe.apply(denoised)

        # D. Binarization & Cleanup
        binary_raw = cv2.adaptiveThreshold(amplified, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY_INV,BLOCK_SIZE, C_VALUE)
        binary_clean = cv2.medianBlur(binary_raw, MEDIAN_SIZE)
        # E. Collect remaining for Stitched Grids
        binary_list.append(prep_for_stitch(binary_clean, is_gray=True))

    final_binary_rgb = create_master_grid(binary_list)  # RGB
    print("params:", CLAHE_LIMIT, BLOCK_SIZE, C_VALUE, MEDIAN_SIZE)
    return final_binary_rgb


def generate_tile_glb_bytes(color_bgr: np.ndarray, depth_rgb: np.ndarray, target_size=(512, 512)):
    color_bgr = cv2.resize(color_bgr, target_size, interpolation=cv2.INTER_AREA)
    depth_rgb = cv2.resize(depth_rgb, target_size, interpolation=cv2.INTER_AREA)


    depth_src = cv2.flip(depth_rgb, 0)
    depth_map = depth_src[:, :, 0] if len(depth_src.shape) == 3 else depth_src

    h, w = depth_map.shape
    depth_norm = depth_map.astype(np.float32) / 255.0


    z_top = 30.0 - (depth_norm * 10.0)

    # 2. Create Grid Vertices
    x = np.linspace(0, w - 1, w)
    y = np.linspace(0, h - 1, h)
    xv, yv = np.meshgrid(x, y)

    v_top = np.stack([xv.ravel(), yv.ravel(), z_top.ravel()], axis=1)
    v_bot = np.stack([xv.ravel(), yv.ravel(), np.zeros_like(z_top.ravel())], axis=1)
    all_vertices = np.vstack([v_top, v_bot])

    # 3. Dedicated UV Mapping
    # TOP: Maps the image perfectly across the top surface (0 to 1 range)
    u = xv.ravel() / (w - 1)
    v = yv.ravel() / (h - 1)
    uvs_top = np.stack([u, v], axis=1)

    # BOTTOM & SIDES: Map to a single pixel (0.001 to avoid edge bleeding)
    # This prevents the top image from stretching down the vertical walls.
    uvs_bot = np.full_like(uvs_top, 0.001)
    all_uvs = np.vstack([uvs_top, uvs_bot])

    # 4. Define Faces (Top and Bottom)
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

    # 5. Side Wall Faces (Corrected Variables)
    side_faces = []
    idx_t = np.arange(h * w).reshape(h, w)
    idx_b = idx_t + (h * w)

    for i in range(w - 1):
        # Top edge wall
        side_faces.extend([[idx_t[0, i], idx_b[0, i], idx_t[0, i + 1]],[idx_b[0, i], idx_b[0, i + 1], idx_t[0, i + 1]]])
        # Bottom edge wall
        side_faces.extend([[idx_t[-1, i], idx_t[-1, i + 1], idx_b[-1, i]],[idx_b[-1, i], idx_t[-1, i + 1], idx_b[-1, i + 1]]])
    for j in range(h - 1):
        # Left edge wall
        side_faces.extend([[idx_t[j, 0], idx_t[j + 1, 0], idx_b[j, 0]],[idx_b[j, 0], idx_t[j + 1, 0], idx_b[j + 1, 0]]])
        # Right edge wall
        side_faces.extend([[idx_t[j, -1], idx_b[j, -1], idx_t[j + 1, -1]],[idx_b[j, -1], idx_b[j + 1, -1], idx_t[j + 1, -1]]])
    
    

    all_faces = np.vstack([f_top, f_bot, np.array(side_faces)])


    rgb_img = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    material = trimesh.visual.texture.SimpleMaterial(image=pil_img)
    visuals = trimesh.visual.TextureVisuals(uv=all_uvs, material=material)

    mesh = trimesh.Trimesh(vertices=all_vertices, faces=all_faces, visual=visuals, process=False)
    

    return mesh.export(file_type="glb")

def upload_glb_bytes(textile_id: str, glb_bytes: bytes):
    bucket = get_bucket()

    file_name = f"{textile_id}_3d.glb"
    storage_path = f"teletex/{textile_id}/model/{file_name}"

    blob = bucket.blob(storage_path)
    blob.upload_from_string(glb_bytes, content_type="model/gltf-binary")

    return storage_path, file_name


def upload_stitched_binary_image(textile_id: str, binary_rgb: np.ndarray):
    bucket = get_bucket()

    file_name = f"{textile_id}_binary.png"
    storage_path = f"teletex/{textile_id}/binary/{file_name}"

    blob = bucket.blob(storage_path)

    binary_bgr = cv2.cvtColor(binary_rgb, cv2.COLOR_RGB2BGR)

    ok, buf = cv2.imencode(".png", binary_bgr)
    if not ok:
        raise ValueError("Failed to encode binary image.")

    blob.upload_from_string(buf.tobytes(), content_type="image/png")

    return storage_path, file_name


def generate_and_upload_glb(textile_id):
    textile_path = get_textile_path(textile_id)
    color_bgr = storage_path_to_bgr(textile_path)

    vt_paths = get_vt_paths(textile_id)
    vt_bgr_list = [storage_path_to_bgr(p) for p in vt_paths]

    depth_rgb = build_binary_from_vtimages(vt_bgr_list, X_START, Y_START, SIDE_LENGTH)

    binary_path, binary_name = upload_stitched_binary_image(textile_id, depth_rgb)

    glb_bytes = generate_tile_glb_bytes(color_bgr, depth_rgb)

    glb_path, glb_name = upload_glb_bytes(textile_id, glb_bytes)

    return glb_path, binary_path