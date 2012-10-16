#-*- coding: utf-8 -*-
from django.utils.translation import ugettext_lazy as _
from django.db import models
from shop.util.fields import CurrencyField
from shop.models import Order


class Confirmation(models.Model):
    """
    Model to store every confirmation for successful or failed payments.
    """
    class Meta:
        verbose_name = _('Viveum Confirmation')

    order = models.ForeignKey(Order,
        verbose_name=_('Unique identifier for submitted payments'))
    status = models.IntegerField(
        verbose_name=_('The PSP\'s return status'))
    acceptance = models.CharField(max_length=20, blank=True,
        verbose_name=_('Acquirer\'s acceptance (authorisation) code.'))
    payid = models.IntegerField(
        verbose_name=_('The PSP\'s unique transaction reference.'))
    merchant_comment = models.TextField(null=True, blank=True,
        verbose_name=_('Additional comments from the merchant'))
    ncerror = models.IntegerField(
        verbose_name=_('The PSP\'s error code'))
    cn = models.CharField(max_length=255,
        verbose_name=_('Card holder (customer) name'))
    amount = CurrencyField()
    ipcty = models.CharField(blank=True, max_length=2,
        verbose_name=_('Originating country of the IP address'))
    currency = models.CharField(max_length=3,
        verbose_name=_('Currency of the transaction'))
    cardno = models.CharField(max_length=21,
        verbose_name=_('The last 4 digits of the customers credit card number'))
    brand = models.CharField(max_length=25,
        verbose_name=_('Brand of a credit/debit/purchasing card'))
    origin = models.CharField(max_length=10,
        verbose_name=_('Origin for this confirmation'))

    @staticmethod
    def get_meta_fields():
        return Confirmation._meta.fields
