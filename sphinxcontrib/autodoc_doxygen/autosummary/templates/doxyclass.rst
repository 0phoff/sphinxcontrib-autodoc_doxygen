{{ name }}
{{ underline }}

.. autodoxyclass:: {{ fullname }}
   :members:

   {% if methods or statics%}
   .. rubric:: Methods

   .. autodoxysummary::
   {% for item in methods %}
      ~{{ fullname }}::{{ item }}
   {%- endfor %}
   {% for item in statics %}
      ~{{ fullname }}::{{ item }}
   {%- endfor %}
   {% endif %}

   {% if enums %}
   {% for enum in enums %}
   .. autodoxyenum:: {{ enum }}
   {% endfor %}
   {% endif %}
