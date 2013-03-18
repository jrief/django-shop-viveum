# -*- coding: utf-8 -*-
from django import forms
from viveum.models import Confirmation


class OrderStandardForm(forms.Form):
    """
    Form used to transfer hidden data from the shop to the PSP.
    """
    def __init__(self, *args, **kwargs):
        initial = kwargs.pop('initial')
        kwargs['auto_id'] = False
        super(OrderStandardForm, self).__init__(*args, **kwargs)
        for field, value in initial.iteritems():
            self.fields[field] = forms.CharField(widget=forms.HiddenInput, initial=value)


class ConfirmationForm(forms.ModelForm):
    """
    Form holding confirmation data sent by PSP when a payment was successful.
    """
    class Meta:
        model = Confirmation

    orderid = forms.IntegerField()
    shasign = forms.CharField(min_length=40)
