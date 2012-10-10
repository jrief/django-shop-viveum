# -*- coding: utf-8 -*-
from django import forms


class OrderStandardForm(forms.Form):
    """
    Form used to transfer hidden data from the shop to Viveum.
    """
    def __init__(self, *args, **kwargs):
        initial = kwargs.pop('initial')
        super(OrderStandardForm, self).__init__(*args, **kwargs)
        for field, value in initial.iteritems:
            self.fields[field] = forms.CharField(widget=forms.HiddenInput, initial=value)
