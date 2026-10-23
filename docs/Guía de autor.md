# Guía de autor — Moodle Course as Code

Cómo escribir contenido para el sistema: manifests, Markdown soportado,
convenciones y flujo de publicación. Complementa la
[especificación](Especificación%20Moodle%20Course%20as%20Code%20v0.2.md) (§6,
§8, §14, §20).

## Estructura del repo de contenidos

```text
course.yml                  # manifiesto del curso
books/
  ut03-mvc/
    book.yml                # manifiesto del Book
    01-introduccion.md      # capítulos
    02-mvc.md
    assets/
      diagrama.svg          # imágenes del Book
```

## `course.yml`

```yaml
id: dwes
title: Desarrollo Web en Entorno Servidor
books:
  - id: ut03-mvc
    path: books/ut03-mvc
```

## `book.yml`

```yaml
id: ut03-mvc
type: book
title: MVC y patrones de diseño
description: Introducción al patrón MVC y su aplicación en web.
summary: Resumen corto para el catálogo.
tags: [php, mvc]
audience: 2º DAW
cover: assets/cover.png        # opcional
numbering: numbers             # numbers | none (enum)
chapters:
  - id: introduccion           # id estable: NUNCA se renombra tras publicar
    title: Introducción
    file: 01-introduccion.md
  - id: mvc
    title: El patrón MVC
    file: 02-mvc.md
```

Los metadatos de catálogo (`summary`, `tags`, `audience`) son obligatorios: el
validador los reporta y el catálogo los muestra en Moodle. **No hay campo
`version`**: la versión la pone Git (tags).

## Markdown soportado

CommonMark con extensiones: **tablas**, **tachado** (`~~texto~~`) y bloques de
código con lenguaje (` ```php `, resaltado con estilos inline). Componentes:

```markdown
:::note
Los apuntes admiten admonitions: note, warning, tip, important.
:::

[Ir al modelo](03-model.md)            # enlace interno por NOMBRE DE ARCHIVO
[Ir al modelo §persistencia](03-model.md#persistencia)   # con ancla
![Diagrama](assets/diagrama.svg)       # imágenes bajo assets/
```

- Los enlaces internos apuntan al **archivo `.md` del capítulo destino** (no a
  su id): el renderer los convierte en enlaces al capítulo Moodle en el
  despliegue y a la ruta local en la preview. Las anclas `#seccion` se conservan.
- Los assets viven en `assets/` y se referencian con ruta relativa.
- **Nunca** escribas HTML ni clases CSS: el estilo lo pone el tema (§14).

## Validación

```bash
courseascode validate              # working tree
courseascode validate --ref <tag>  # un tag/rama/commit concreto
```

Reglas comprobadas (§20): YAML válido · IDs únicos de books y capítulos ·
archivos de capítulos existen · assets y cover existen · enlaces internos `.md`
resolubles contra el manifest · contenedores `:::` cerrados · metadatos de
catálogo presentes · `numbering` válido. La salida es `✓/✗` por categoría con
`archivo:línea — mensaje`; exit 1 si hay errores. En CI: status check en PRs.

## Previsualizar

```bash
courseascode preview books/ut03-mvc          # http://localhost:3000
courseascode preview ut03-mvc --ref v1.0.0   # un tag concreto
```

Guarda en el editor y refresca el navegador: la preview re-renderiza en cada
petición, sin reiniciar nada. Usa exactamente el mismo renderer que el
despliegue.

## Publicar: versionado con Git (§8)

1. Trabaja en tu **rama personal** (`git checkout -b juan`). La versión derivada
   se calcula sola: tag base oficial + commits propios → `1.2.0+juan.3`.
2. Para publicar oficialmente: PR a `main`. Un PR MINOR requiere 2
   aprobaciones y `validate` en verde es bloqueante (§10.2/§32.12).
3. Tras el merge, el coordinador crea el tag: `book/ut03-mvc/v1.0.0`.
4. **Los tags son inmutables** (§8.3): nunca se reescribe un tag publicado; un
   error se corrige siempre hacia delante con un PATCH (`v1.0.1`).

Solo las versiones **taggeadas** aparecen en el catálogo de Moodle; el trabajo
en progreso (HEAD) nunca se muestra ni se despliega por defecto.

## Hotfix crítico (§11.1)

Nunca se corrige el pasado: rama de hotfix desde el tag afectado, cambio
mínimo, PR con carril rápido (1 aprobación, `validate` sigue siendo
bloqueante), merge + tag PATCH inmediato. La **severidad y el recall** los
declara el coordinador con `courseascode release mark` — es estado
administrativo, no Git (ver la Guía de operación).
