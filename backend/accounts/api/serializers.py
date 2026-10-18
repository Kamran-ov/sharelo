from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    email = serializers.CharField(allow_blank=True)
    password = serializers.CharField(trim_whitespace=False, allow_blank=True)
    display_name = serializers.CharField(allow_blank=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(allow_blank=True)
    password = serializers.CharField(trim_whitespace=False, allow_blank=True)


class GoogleSerializer(serializers.Serializer):
    id_token = serializers.CharField()
