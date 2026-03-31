from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import TextileCreateSerializer
from .services import verify_storage_files, write_metadata,update_textile_main_doc
from .process3d import generate_and_upload_glb

from datetime import timedelta

from config.firebase_config import get_bucket, get_db

class UploadTextile(APIView):
    def post(self, request):
        print("request.data:", request.data)
        serializer = TextileCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        textile_id = serializer.validated_data["textileId"]
        title = serializer.validated_data["title"]

        try:
            verify_storage_files(textile_id)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        write_metadata(textile_id, title)

        update_textile_main_doc(
            textile_id=textile_id,
            status="processing",
            stage="starting",
            progress=0
        )

        def progress_callback(stage, progress, **kwargs):
            update_textile_main_doc(
                textile_id=textile_id,
                status="processing",
                stage=stage,
                progress=progress,
                **kwargs
            )

        try:
            result = generate_and_upload_glb(
                textile_id,
                progress_callback=progress_callback
            )

            update_textile_main_doc(
                textile_id=textile_id,
                status="ready",
                stage="done",
                progress=4,
                textilePath=result["textile_path"],
                stitched_path=result["stitched_path"],
                binary_path=result["binary_path"],
                glb_path=result["glb_path"],
            )

            return Response(
                {
                    "textileId": textile_id,
                    "title": title,
                    "status": "ready",
                    "stage": "done",
                    "progress": 4,
                    "textilePath": result["textile_path"],
                    "stitchedPath": result["stitched_path"],
                    "binaryPath": result["binary_path"],
                    "glbPath": result["glb_path"],
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            update_textile_main_doc(
                textile_id=textile_id,
                status="failed",
                stage="failed"
            )
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class GetPreview(APIView):
    def get(self, request, textile_id):
        try:
            db = get_db()
            bucket = get_bucket()

            doc = db.collection("textile").document(textile_id).get()

            if not doc.exists:
                return Response(
                    {
                        "textileId": textile_id,
                        "status": "waiting",
                        "stage": "waiting",
                        "progress": 0,
                        "ready": False,
                        "originalImageUrl": None,
                        "stitchedImageUrl": None,
                        "binaryImageUrl": None,
                        "glbUrl": None,
                    },
                    status=status.HTTP_200_OK
                )

            data = doc.to_dict()

            textile_path = data.get("textilePath")
            stitched_path = data.get("stitched_path")
            binary_path = data.get("binary_path")
            glb_path = data.get("glb_path")
            model_preview_path = data.get("model_preview_path")
            status_value = data.get("status")
            stage = data.get("stage")
            progress = data.get("progress", 0)

            original_url = None
            stitched_url = None
            binary_url = None
            glb_url = None
            model_preview_url = None

            if textile_path:
                original_url = bucket.blob(textile_path).generate_signed_url(
                    expiration=timedelta(hours=1),
                    method="GET"
                )

            if stitched_path:
                stitched_url = bucket.blob(stitched_path).generate_signed_url(
                    expiration=timedelta(hours=1),
                    method="GET"
                )

            if binary_path:
                binary_url = bucket.blob(binary_path).generate_signed_url(
                    expiration=timedelta(hours=1),
                    method="GET"
                )

            if glb_path:
                glb_url = bucket.blob(glb_path).generate_signed_url(
                    expiration=timedelta(hours=1),
                    method="GET"
                )

            if model_preview_path:
                model_preview_url = bucket.blob(model_preview_path).generate_signed_url(
                    expiration=timedelta(hours=1),
                    method="GET"
                )

            return Response(
                {
                    "textileId": textile_id,
                    "title": data.get("title"),
                    "status": status_value,
                    "stage": stage,
                    "progress": progress,
                    "ready": status_value == "ready",
                    "originalImageUrl": original_url,
                    "stitchedImageUrl": stitched_url,
                    "binaryImageUrl": binary_url,
                    "glbUrl": glb_url,
                    "modelPreviewUrl": model_preview_url,
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class GetTextiles(APIView):
    def get(self, request):
        try:
            db = get_db()
            bucket = get_bucket()
            docs = db.collection("textile").stream()

            results = []

            for doc in docs:
                data = doc.to_dict()

                if data.get("status") != "ready":
                    continue

                textile_path = data.get("textilePath")
                textile_image_url = None

                if textile_path:
                    blob = bucket.blob(textile_path)
                    textile_image_url = blob.generate_signed_url(expiration=timedelta(hours=1),method="GET")

                results.append({
                    "textileId": doc.id, "title": data.get("title"), "textilePath": textile_path, "textileImgSignedUrl": textile_image_url,})

            return Response({"items": results}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)},status=status.HTTP_500_INTERNAL_SERVER_ERROR)


  
class GetModel(APIView):
    def get(self, request, textile_id):
        try:
            db = get_db()
            bucket = get_bucket()

            doc = db.collection("textile").document(textile_id).get()

            if not doc.exists:
                return Response({"error": "Textile not found."}, status=status.HTTP_404_NOT_FOUND)

            data = doc.to_dict()
            glb_path = data.get("glb_path")

            if not glb_path:
                return Response({"error": "Model not found."}, status=status.HTTP_404_NOT_FOUND)

            blob = bucket.blob(glb_path)
            glb_url = blob.generate_signed_url(expiration=timedelta(hours=1),method="GET")

            return Response({"textileId": doc.id, "title": data.get("title"), "glbSignedUrl": glb_url,}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
