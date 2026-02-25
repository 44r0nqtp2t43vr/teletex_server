from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import TextileCreateSerializer
from .services import create_textile, upload_to_storage, add_textile_image_doc, add_vtimage_doc
 

class UploadTextile(APIView):
    def post(self, request):
        serializer = TextileCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        title = serializer.validated_data["title"]
        textile_image = serializer.validated_data["textile_image"]
        vtimages = serializer.validated_data["vtimages"]

        if len(vtimages) != 16:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            textile_id = create_textile(title)
        except ValueError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        t_path = upload_to_storage(textile_id, "textile_image", textile_image, textile_image.name)
        add_textile_image_doc(textile_id, t_path, textile_image.name)

        vt_results = []
        for i in range(16):
            f = vtimages[i]
            path = upload_to_storage(textile_id, "vt_image", f, f.name)
            add_vtimage_doc(textile_id, i + 1, path, f.name)
            vt_results.append({"index": i + 1, "name": f.name, "storagePath": path})

        return Response(status=status.HTTP_201_CREATED )