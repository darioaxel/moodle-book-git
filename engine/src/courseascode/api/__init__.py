"""FastAPI: endpoints que consume el plugin Moodle.

Los endpoints de catálogo de la Fase 5 (ENG-053) viven en ``web/app.py``,
que es la única app FastAPI del servicio (la preview HTML y el catálogo JSON
conviven en ``create_app``). Los endpoints REST de despliegue (ENG-079:
``POST /deploy``, ``POST /deployment/plan``, ``GET /deployment/status``,
``GET /deployment/where``) se construyen en ``courseascode.api.deployment``
y se montan desde ``web.app.create_app``. El webhook (ENG-093) llegará en
Fase 8.
"""
