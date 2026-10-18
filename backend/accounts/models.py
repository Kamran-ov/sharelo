from django.conf import settings
from django.db import models


class Profile(models.Model):
    """One person across every group; their per-group identity is `ledger.Member`."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    display_name = models.CharField(max_length=100)
    main_group = models.ForeignKey(
        "ledger.Group", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
