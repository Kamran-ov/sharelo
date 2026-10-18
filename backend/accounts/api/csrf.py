from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.views import APIView


# DRF exempts every APIView from CsrfViewMiddleware and SessionAuthentication only checks
# the token for an already-signed-in user, so anonymous POSTs (login, register) need this.
@method_decorator(csrf_protect, name="dispatch")
class CsrfProtectedAPIView(APIView):
    pass
