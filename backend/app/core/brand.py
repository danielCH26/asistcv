"""Marca de eptus — lo que el backend necesita para hablar con la marca.

La marca vive en el frontend (``frontend/src/lib/components/Logo.svelte`` y
``frontend/static/logo-mark.svg``). Este módulo es la copia del lado del
servidor: los correos HTML se arman con strings (sin motor de plantillas), y
ahí no hay forma de importar un SVG del frontend — así que la geometría de la
"e" vive duplicada, en los dos lados, a propósito.

Si cambia la marca, cambian los dos lados en el mismo commit.
"""

from __future__ import annotations

#: Nombre de la marca.
NAME = "eptus"

#: La "e" geométrica: anillo + barra, con la boca abierta abajo a la derecha.
#: viewBox 0 0 32 32, trazo 4.5. El arco arranca en el extremo DERECHO de la
#: barra (3 o'clock) y recorre casi todo el anillo hasta 45 grados.
MARK_SVG = (
    '<svg width="26" height="26" viewBox="0 0 32 32" fill="none" '
    'stroke="{color}" stroke-width="4.5" stroke-linecap="round" '
    'style="vertical-align:-5px;margin-right:8px">'
    '<path d="M25.5 16 A9.5 9.5 0 1 0 22.72 22.72"/>'
    '<path d="M6.5 16 H25.5"/>'
    "</svg>"
)

#: Tinta y color de acción del tema claro (los mismos hex de app.css).
ACTION = "#4f46e5"
ACTION_HOVER = "#4338ca"
INK = "#1c1c2b"
INK_MUTED = "#4c4c63"


def brand_lockup(color: str = ACTION) -> str:
    """Marca + nombre, para la cabecera de los correos."""
    return (
        f'{MARK_SVG.format(color=color)}'
        f'<strong style="font-size:19px;letter-spacing:-.02em;color:{INK}">{NAME}</strong>'
    )
