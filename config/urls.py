from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('t/', include('apps.panel.urls')),
    path('j/', include('apps.live.urls')),  # students join live sessions here
    path('', include('apps.site.urls')),
]
