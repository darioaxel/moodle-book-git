# Proyecto: Moodle Course as Code — Beta 0.1

## 1. Objetivo

Desarrollar una primera versión funcional de un sistema denominado provisionalmente **Moodle Course as Code** cuyo objetivo final es permitir definir un curso Moodle mediante archivos versionados en Git y utilizar Moodle como plataforma de despliegue.

La arquitectura debe diseñarse desde el principio para poder evolucionar posteriormente desde:

* Books

hacia:

* Pages
* Quizzes
* Assignments
* Resources
* Activities
* estructura de cursos
* configuración de actividades
* metadatos curriculares
* releases de cursos

Pero la **Beta 0.1 SOLO debe implementar Books**.

El principio fundamental es:

> Git es la fuente de verdad del contenido docente. Moodle es la plataforma de publicación y ejecución.

No se debe convertir Moodle en el editor principal del contenido.

---

# 2. Objetivos de la Beta 0.1

La beta debe permitir este flujo:

```text
Autor
  │
  ▼
Markdown
  │
  ▼
Git
  │
  ├── historial
  ├── branches
  ├── tags
  └── commits
  │
  ▼
Course Manifest
  │
  ▼
Preview
  │
  ▼
Publish
  │
  ▼
Moodle Book
  │
  ▼
Alumnado
```

El usuario debe poder:

1. Crear un Book mediante Markdown.
2. Organizarlo en capítulos/secciones.
3. Ver una previsualización HTML antes de publicar.
4. Utilizar un estilo visual propio.
5. Versionar el contenido con Git.
6. Definir qué versión se publica en cada curso Moodle.
7. Publicar/sincronizar el Book con Moodle.
8. Ver desde Moodle qué versión está publicada.
9. Actualizar el Book a una nueva versión.
10. Volver a desplegar una versión anterior.

---

# 3. Principio arquitectónico fundamental

Separar claramente:

```text
SOURCE
   ↓
CONTENT
   ↓
RELEASE
   ↓
DEPLOYMENT
   ↓
MOODLE
```

No almacenar el contenido Markdown dentro de la base de datos Moodle como fuente maestra.

Moodle debe almacenar únicamente:

* referencia al repositorio;
* referencia a la versión;
* identificador del contenido;
* relación con el curso;
* identificador del Book Moodle;
* información del último despliegue.

---

# 4. Tecnologías propuestas

La primera implementación debe utilizar tecnologías sencillas y ampliamente mantenibles.

## Backend / herramienta

Preferencia:

* Python
* FastAPI
* GitPython o ejecución controlada de Git
* PyYAML
* Markdown parser compatible con CommonMark
* Pygments para código
* Jinja2 para templates

Si se considera más adecuado implementar el componente como plugin Moodle, utilizar PHP siguiendo las APIs oficiales de Moodle.

La arquitectura debe separar claramente:

```text
Content Engine
Git Adapter
Renderer
Manifest Parser
Moodle Adapter
Deployment Engine
```

No mezclar lógica de Git con lógica Moodle.

---

# 5. Estructura inicial del repositorio

Crear un repositorio de contenidos con una estructura como:

```text
dwes-content/
│
├── course.yml
│
├── books/
│   │
│   └── ut03-mvc/
│       │
│       ├── book.yml
│       │
│       ├── 01-introduccion.md
│       ├── 02-mvc.md
│       ├── 03-model.md
│       ├── 04-view.md
│       ├── 05-controller.md
│       └── assets/
│           ├── mvc.svg
│           └── ejemplo.png
│
└── README.md
```

No utilizar todavía una estructura excesivamente compleja.

---

# 6. Manifest del curso

Crear un archivo:

```yaml
course.yml
```

Ejemplo:

```yaml
id: dwes
title: Desarrollo Web en Entorno Servidor

books:
  - id: ut03-mvc
    path: books/ut03-mvc
```

Este archivo representa qué contenidos pertenecen al curso.

En futuras versiones deberá poder contener:

```yaml
books:
pages:
quizzes:
assignments:
resources:
```

pero en Beta 0.1 únicamente implementar `books`.

---

# 7. Manifest del Book

Cada Book debe tener:

```text
books/ut03-mvc/book.yml
```

Ejemplo:

```yaml
id: ut03-mvc
type: book

title: MVC y patrones de diseño

version: 1.2.0

description: >
  Introducción al patrón MVC y su aplicación
  en aplicaciones web.

chapters:
  - id: introduccion
    title: Introducción
    file: 01-introduccion.md

  - id: mvc
    title: MVC
    file: 02-mvc.md

  - id: model
    title: Model
    file: 03-model.md

  - id: view
    title: View
    file: 04-view.md

  - id: controller
    title: Controller
    file: 05-controller.md
```

La propiedad `id` debe ser estable.

El título puede cambiar.

La posición del capítulo puede cambiar.

El `id` debe permanecer estable siempre que conceptualmente sea el mismo capítulo.

---

# 8. Versionado

No utilizar Git únicamente como backup.

Utilizar Git como sistema real de versionado.

Ejemplo:

```text
commit
   ↓
commit
   ↓
commit
   ↓
tag
```

Los Books deben poder identificarse mediante:

```text
book id
version
git commit
git tag
```

Ejemplo:

```text
ut03-mvc
version: 1.2.0
tag: book/ut03-mvc/v1.2.0
commit: 8f31a2c
```

La versión semántica será:

```text
MAJOR.MINOR.PATCH
```

Reglas iniciales:

* PATCH: correcciones menores.
* MINOR: contenido nuevo compatible.
* MAJOR: cambios estructurales o pedagógicos importantes.

No es necesario automatizar todavía el incremento de versiones.

---

# 9. Concepto fundamental: Release

Separar:

```text
CONTENT VERSION
```

de:

```text
MOODLE DEPLOYMENT
```

Un Book puede existir en Git:

```text
v1.0.0
v1.1.0
v1.2.0
v2.0.0
```

pero cada curso puede utilizar una versión diferente.

Ejemplo:

```text
Curso DWES 2025-2026
    UT03 → v1.1.0

Curso DWES 2026-2027
    UT03 → v1.2.0
```

No asumir que "última versión Git" significa "versión publicada".

---

# 10. Deployment manifest

Crear una estructura para representar qué versión se publica en cada curso.

Por ejemplo:

```text
deployments/
    2026-2027.yml
```

Contenido:

```yaml
course:
  id: dwes
  academic_year: 2026-2027

books:

  - id: ut03-mvc
    version: 1.2.0
    git_ref: book/ut03-mvc/v1.2.0
```

Este archivo es extremadamente importante.

Debe ser la fuente de verdad de:

> Qué versión de cada material se publica en cada curso.

---

# 11. Ejemplo completo

Repositorio:

```text
dwes-content/
```

Contenido:

```text
books/
    ut03-mvc/
        book.yml
        01-introduccion.md
        02-mvc.md
        03-model.md
        04-view.md
        05-controller.md
```

Versiones:

```text
book/ut03-mvc/v1.0.0
book/ut03-mvc/v1.1.0
book/ut03-mvc/v1.2.0
```

Deployment:

```yaml
course:
  id: dwes
  academic_year: 2026-2027

books:
  - id: ut03-mvc
    version: 1.2.0
    git_ref: book/ut03-mvc/v1.2.0
```

Esto debe permitir reconstruir exactamente el estado publicado.

---

# 12. Preview

Implementar una interfaz web de preview.

Ejemplo:

```text
┌─────────────────────────────────────────────┐
│ Moodle Course as Code                       │
├─────────────────────────────────────────────┤
│ DWES                                        │
│                                             │
│ UT03 - MVC                                  │
│ Version 1.2.0                               │
│ Commit 8f31a2c                               │
│                                             │
│ ┌───────────────┐ ┌───────────────────────┐ │
│ │ Contenido     │ │ Preview               │ │
│ │               │ │                       │ │
│ │ Introducción  │ │ # MVC                 │ │
│ │ MVC           │ │                       │ │
│ │ Model         │ │ ...                   │ │
│ │ View          │ │                       │ │
│ │ Controller    │ │                       │ │
│ └───────────────┘ └───────────────────────┘ │
└─────────────────────────────────────────────┘
```

La preview debe parecerse visualmente al Book Moodle final.

No mostrar únicamente Markdown convertido a HTML sin estilo.

---

# 13. Sistema de estilos

Crear un renderer HTML propio.

Debe existir una capa:

```text
Markdown
   ↓
AST / parsed Markdown
   ↓
HTML semántico
   ↓
Theme
   ↓
Preview
```

El estilo no debe estar mezclado con el Markdown.

Esto permitirá posteriormente crear:

```text
theme-default
theme-dwes
theme-centro
```

El contenido:

```markdown
# MVC

Texto...
```

no debe contener clases CSS específicas del tema.

---

# 14. Componentes Markdown iniciales

La Beta 0.1 debe soportar como mínimo:

* títulos H1-H6;
* párrafos;
* negrita;
* cursiva;
* enlaces;
* listas;
* listas numeradas;
* tablas;
* blockquotes;
* código inline;
* bloques de código;
* imágenes;
* separación horizontal;
* enlaces internos;
* admonitions.

Implementar admonitions mediante una sintaxis sencilla.

Por ejemplo:

```markdown
:::note
Recuerda que MVC separa responsabilidades.
```
