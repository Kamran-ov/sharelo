from django.db import models


class Profile(models.Model):
    """Stub: ticket 006 adds the User link, main group and group links."""

    email = models.EmailField(unique=True)
