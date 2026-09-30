from django import forms
from django.conf import settings
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import views as auth_views


class LoginRecordarForm(auth_forms.AuthenticationForm):
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "login-checkbox-input"},
        ),
    )


class LoginConRecordarView(auth_views.LoginView):
    form_class = LoginRecordarForm
    template_name = "dashboard/registration/login.html"

    def form_valid(self, form):
        respuesta = super().form_valid(form)

        if form.cleaned_data["remember_me"]:
            self.request.session.set_expiry(
                settings.SESION_RECORDAR_DIAS * 24 * 60 * 60
            )
        else:
            self.request.session.set_expiry(0)

        self.request.session.save()

        return respuesta