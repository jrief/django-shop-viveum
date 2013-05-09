#-*- coding: utf-8 -*-
from django.conf import settings
from django.template.loader import render_to_string
from django.contrib.sites.models import Site
from django.views.generic import TemplateView
from django.template.context import RequestContext
from django.http import HttpResponse


class PaymentZoneView(TemplateView):
    """
    This view renders a page, which itself is used by Viveum as a template to
    add the payment entry forms.
    """
    template_name = 'viveum/payment_zone.html'

    def get_context_data(self, **kwargs):
        """
        In the render context, prepend the local hostname to STATIC_URL.
        This is required, since the customer receives this page by Viveum,
        and thus images and style-sheets must be accessed by their full
        qualified URL.
        """
        context = RequestContext(self.request)
        if 'STATIC_URL' in settings.VIVEUM_PAYMENT:
            for k in range(len(context.dicts)):
                if 'STATIC_URL' in context.dicts[k]:
                    context.dicts[k].update({'STATIC_URL': settings.VIVEUM_PAYMENT.get('STATIC_URL')})
        return context

    def get(self, *args, **kwargs):
        """
        Replaces all UTF-8 characters by HTML Decimal's since the Viveum template
        rendering engine otherwise gets confused.
        """
        context = self.get_context_data(**kwargs)
        html = render_to_string(self.get_template_names(), context_instance=context)
        return HttpResponse(html.encode('ascii', 'xmlcharrefreplace'))
