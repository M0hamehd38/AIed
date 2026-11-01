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


# ---------------------------------------------------------------- the signed-in user's own account
DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalize_mobile(raw):
    """Iranian mobile numbers in any common spelling (Persian digits, spaces, +98, 0098) as 09xxxxxxxxx."""
    v = ''.join(ch for ch in (raw or '').translate(DIGITS) if ch.isdigit() or ch == '+')
    for prefix in ('+98', '0098', '98'):
        if v.startswith(prefix) and len(v) - len(prefix) == 10:
            v = '0' + v[len(prefix):]
            break
    if len(v) == 10 and v.startswith('9'):
        v = '0' + v
    return v


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['full_name', 'mobile', 'sms_opt_in']
        error_messages = {'full_name': {'required': 'نام خود را وارد کنید.'}}

    def clean_full_name(self):
        name = ' '.join(self.cleaned_data['full_name'].split())
        if len(name) < 3:
            raise forms.ValidationError('نام خود را کامل وارد کنید.')
        return name

    def clean_mobile(self):
        raw = self.cleaned_data.get('mobile', '')
        if not raw.strip():
            return ''
        v = normalize_mobile(raw)
        if not (len(v) == 11 and v.startswith('09')):
            raise forms.ValidationError('شماره‌ی موبایل را مثل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.')
        return v

    def clean(self):
        data = super().clean()
        if data.get('sms_opt_in') and not data.get('mobile'):
            self.add_error('mobile', 'برای دریافت پیامک، شماره‌ی موبایل لازم است.')
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if 'mobile' in self.changed_data:
            user.mobile_verified = False   # a new number has to be confirmed again
        if commit:
            user.save()
        return user


class _CurrentPasswordMixin:
    """Changing sign-in details asks for the current password first."""

    def clean_current_password(self):
        pw = self.cleaned_data.get('current_password', '')
        if not self.user.check_password(pw):
            raise forms.ValidationError('رمز عبور فعلی درست نیست.')
        return pw


class EmailChangeForm(_CurrentPasswordMixin, forms.Form):
    email = forms.EmailField(label='ایمیل جدید', error_messages={'required': 'ایمیل جدید را وارد کنید.', 'invalid': 'ایمیل معتبر وارد کنید.'})
    current_password = forms.CharField(label='رمز عبور فعلی', error_messages={'required': 'رمز عبور فعلی را وارد کنید.'})

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if email == self.user.email:
            raise forms.ValidationError('این همان ایمیل فعلی شماست.')
        if User.objects.filter(email=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError('این ایمیل برای حساب دیگری ثبت شده است.')
        return email

    def save(self):
        self.user.email = self.cleaned_data['email']
        self.user.save(update_fields=['email'])
        return self.user


class PasswordChangeForm(_CurrentPasswordMixin, forms.Form):
    current_password = forms.CharField(label='رمز عبور فعلی', error_messages={'required': 'رمز عبور فعلی را وارد کنید.'})
    new_password = forms.CharField(label='رمز عبور جدید', error_messages={'required': 'رمز عبور جدید را وارد کنید.'})
    new_password2 = forms.CharField(label='تکرار رمز عبور جدید', error_messages={'required': 'رمز عبور جدید را تکرار کنید.'})

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        new, again = data.get('new_password'), data.get('new_password2')
        if new and again and new != again:
            self.add_error('new_password2', 'دو رمز عبور جدید یکسان نیستند.')
        elif new:
            try:
                password_validation.validate_password(new, self.user)
            except forms.ValidationError as e:
                self.add_error('new_password', e)
        return data

    def save(self):
        self.user.set_password(self.cleaned_data['new_password'])
        self.user.save(update_fields=['password'])
        return self.user
