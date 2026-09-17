from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.urls import reverse


def staff_requerido(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("login"))
        if not request.user.is_staff:
            raise Http404
        return view_func(request, *args, **kwargs)

    return wrapper
