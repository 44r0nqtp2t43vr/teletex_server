from rest_framework import serializers
# from django.core.validators import FileExtensionValidator

class TextileCreateSerializer(serializers.Serializer):
    title = serializers.CharField()

    textile_image = serializers.FileField()

    vtimages = serializers.ListField(child=serializers.FileField())