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

        update_textile_main_doc(textile_id=textile_id, status="processing")

        write_metadata(textile_id, title)

        try:
            glb_path, binary_path = generate_and_upload_glb(textile_id)

            update_textile_main_doc(textile_id=textile_id, status="ready", binary_path=binary_path, glb_path=glb_path)
            return Response(status=status.HTTP_201_CREATED)

        except Exception as e:
            update_textile_main_doc(textile_id=textile_id, status="failed")
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
            glb_path = data.get("glbPath")

            if not glb_path:
                return Response({"error": "Model not found."}, status=status.HTTP_404_NOT_FOUND)

            blob = bucket.blob(glb_path)
            glb_url = blob.generate_signed_url(expiration=timedelta(hours=1),method="GET")

            return Response({"textileId": doc.id, "title": data.get("title"), "glbSignedUrl": glb_url,}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
