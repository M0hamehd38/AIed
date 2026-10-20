from django import forms
from django.contrib.auth import authenticate, password_validation

from .models import User


class LoginForm(forms.Form):
    email = forms.EmailField(error_messages={'required': 'ایمیل را وارد کنید.', 'invalid': 'ایمیل معتبر وارد کنید.'})
    password = forms.CharField(error_messages={'required': 'رمز عبور را وارد کنید.'})

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        self.user = authenticate(self.request, email=data['email'].lower(), password=data['password'])
        if self.user is None:
            # one message for both cases, so the form does not reveal which emails have accounts
            raise forms.ValidationError('ایمیل یا رمز عبور درست نیست.')
        return data


class SignupForm(forms.Form):
    full_name = forms.CharField(min_length=3, max_length=120, error_messages={
        'required': 'نام خود را وارد کنید.', 'min_length': 'نام خود را کامل وارد کنید.'})
    email = forms.EmailField(error_messages={'required': 'ایمیل را وارد کنید.', 'invalid': 'ایمیل معتبر وارد کنید.'})
    password = forms.CharField(error_messages={'required': 'رمز عبور را وارد کنید.'})

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('این ایمیل قبلاً ثبت شده است؛ از بخش «ورود» وارد شوید.')
        return email

    def clean(self):
        data = super().clean()
        if 'password' in data:
            user = User(email=data.get('email', ''), full_name=data.get('full_name', ''))
            try:
                password_validation.validate_password(data['password'], user)
            except forms.ValidationError as e:
                self.add_error('password', e)
        return data

    def save(self):
        d = self.cleaned_data
        return User.objects.create_user(d['email'], d['password'], full_name=d['full_name'].strip(), role=User.Role.TEACHER)
