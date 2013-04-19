#-*- coding: utf-8 -*-
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
        for k in range(len(context.dicts)):
            static_url = context.dicts[k].get('STATIC_URL')
            if static_url and static_url.startswith('/'):
                context.dicts[k] = {'STATIC_URL': 'http://%s%s' % (Site.objects.get_current().domain, static_url)}
        return context

    def get(self, *args, **kwargs):
        """
        Replaces all UTF-8 characters by HTML Decimal's since the Viveum template
        rendering engine otherwise gets confused.
        """
        context = self.get_context_data(**kwargs)
        html = render_to_string(self.get_template_names(), context_instance=context)
        return HttpResponse(html.encode('ascii', 'xmlcharrefreplace'))
