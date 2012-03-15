from {{ original_settings }} import *

{% for k, v in settings_overrides -%}
{{ k }} = {{ v }}
{% endfor -%}

if DEBUG_TOOLBAR:
    TEMPLATE_CONTEXT_PROCESSORS = list(TEMPLATE_CONTEXT_PROCESSORS) + ['django.core.context_processors.debug']

    MIDDLEWARE_CLASSES = list(MIDDLEWARE_CLASSES) + ['debug_toolbar.middleware.DebugToolbarMiddleware']
    INSTALLED_APPS = INSTALLED_APPS + ('debug_toolbar',)
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TEMPLATE_CONTEXT': True,
        'INTERCEPT_REDIRECTS': False,
    }
