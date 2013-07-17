#-*- coding: utf-8 -*-
from django.conf import settings
from django.template.loader import render_to_string
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
        In the render context, prepend the local hostname to STATIC_URL and MEDIA_URL.
        This is required, since Viveum fetches this template and replaces the string
        $$$PAYMENT ZONE$$$ with its own HTML content.
        Thereafter the customer receives this page by Viveum, and thus images and
        style-sheets must be accessed by their full qualified URL.
        """
        context = RequestContext(self.request)
        self._update_context_for_urlkey(context, 'STATIC_URL')
        self._update_context_for_urlkey(context, 'MEDIA_URL')
        return context

    def get(self, *args, **kwargs):
        """
        Replaces all UTF-8 characters by HTML Decimal's since the Viveum template
        rendering engine otherwise gets confused.
        """
        context = self.get_context_data(**kwargs)
        html = render_to_string(self.get_template_names(), context_instance=context)
        return HttpResponse(html.encode('ascii', 'xmlcharrefreplace'))

    def _update_context_for_urlkey(self, context, urlkey):
        if hasattr(settings, urlkey):
            absolute_uri = self.request.build_absolute_uri(getattr(settings, urlkey))
            for k in range(len(context.dicts)):
                if urlkey in context.dicts[k]:
                    context.dicts[k].update({urlkey: absolute_uri})
