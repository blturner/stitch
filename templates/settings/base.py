from {{ original_settings }} import *

{% for k, v in settings_overrides %}
{{ k }} = {{ v }}
{% endfor %}
