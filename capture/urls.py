from django.urls import path
from .views import UploadTextile

urlpatterns = [
    path("textiles/", UploadTextile.as_view()),
]