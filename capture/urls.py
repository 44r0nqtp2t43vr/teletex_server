from django.urls import path
from .views import UploadTextile,GetTextiles, GetModel, GetPreview

urlpatterns = [
    path("textiles/upload/", UploadTextile.as_view(), name="upload-textile"),
    path("textiles/list/", GetTextiles.as_view(), name="get-textiles"),
    path("textiles/<str:textile_id>/model/", GetModel.as_view(), name="get-model"),
    path("textiles/<str:textile_id>/preview/", GetPreview.as_view()),
]