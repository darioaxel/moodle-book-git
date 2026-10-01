# courseascode-engine

Motor Python de **Moodle Course as Code**. Ver el [README del repositorio](../../README.md)
y la [especificación](../../docs/Especificación%20Moodle%20Course%20as%20Code%20v0.2.md).

## Desarrollo

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
make check        # lint + typecheck + tests
```

El CLI (`courseascode --help`) arranca con los comandos de la spec §29 como stubs;
se implementan fase a fase según la [tasklist](../../docs/Tasklist%20—%20Desarrollo%20courseascode-engine.md).

## Configuración (§25)

Variables de entorno obligatorias, fallo ruidoso si falta alguna:

```text
MOODLE_URL=           # URL base de Moodle
MOODLE_TOKEN=         # token de la cuenta técnica (capabilities mínimas)
CONTENT_REPO_URL=     # URL del repo de contenidos
CONTENT_REPO_KEY=     # deploy key de solo lectura
```

Nunca se commitean al repositorio.
