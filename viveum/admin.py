from django.contrib import admin
from models import Confirmation


class ConfirmationAdmin(admin.ModelAdmin):
    list_display = ('order', 'cn', 'status', 'amount')
    readonly_fields = ('order', 'status', 'acceptance', 'payid', 'merchant_comment',
        'ncerror', 'cn', 'amount', 'ipcty', 'currency', 'cardno', 'brand', 'origin')

admin.site.register(Confirmation, ConfirmationAdmin)
