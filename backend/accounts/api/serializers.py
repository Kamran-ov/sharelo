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


class MeProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_name = serializers.CharField()
    email = serializers.CharField()
    main_group_id = serializers.IntegerField(allow_null=True)


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    profile = MeProfileSerializer(allow_null=True)
    guest_memberships = serializers.ListField(child=serializers.IntegerField())
    google_enabled = serializers.BooleanField()
