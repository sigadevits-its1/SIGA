import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def estatico(ruta):
    """
    Igual que {% static %}, pero agrega ?v=<fecha de modificación del archivo>.
    Así, cuando cambia un CSS o JS, el navegador baja la versión nueva
    en lugar de seguir usando la que tenía guardada.
    """
    url = static(ruta)
    archivo = finders.find(ruta)
    if archivo:
        url += f"?v={int(os.path.getmtime(archivo))}"
    return url
