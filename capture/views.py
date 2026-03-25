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

        print("validated_data:", serializer.validated_data)
        try:
            verify_storage_files(textile_id)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        update_textile_main_doc(
            textile_id=textile_id,
            status="processing"
        )

        write_metadata(textile_id, title)

        try:
            glb_path, binary_path = generate_and_upload_glb(textile_id)

            update_textile_main_doc(
                textile_id=textile_id,
                status="ready",
                binary_path=binary_path,
                glb_path=glb_path
            )
            return Response(status=status.HTTP_201_CREATED)

        except Exception as e:
            update_textile_main_doc(
                textile_id=textile_id,
                status="failed"
            )
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )





