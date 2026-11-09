# Estructura de pruebas alpha

## Servidor para pruebas (local)

 * **Moodle**
 ~~https~~ → **http**://192.168.2.253:8088 (sin TLS; https no escucha)
   - Contenedores Docker: `moodle53beta-moodle` (Moodle 6.0dev Build 20261021)
     + `moodle53beta-db` (MariaDB 11.4). Red interna `8088-moodle-v53-beta-test_moodle-internal`.
   - El código vive en el contenedor (`/var/www/moodle`); los plugins en
     `public/local/` son bind mounts desde `/apps/8088-moodle-v5.3-beta-test/`.
   - Curso de pruebas existente: id 2, shortname `CAC-TEST`.
   - **Atención**: `config.php` NO es bind mount — los cambios en él se pierden
     si se recrea el contenedor (ver Guía de operación para replicarlos).

 * **Engine courseascode** (desplegado 2026-11-06)
   - Contenedor `courseascode-engine` en la red interna del Moodle
     (alias `courseascode`), publicado en **http://192.168.2.253:8090**.
   - Contenido: clon de `contenidos-test` en
     `/apps/8088-moodle-v5.3-beta-test/contenidos-test` (owner uid 1000;
     para actualizar tags: `docker exec courseascode-engine git -C /content fetch --tags && git -C ... merge/reset`).
   - Env: `/apps/8088-moodle-v5.3-beta-test/courseascode.env` (600).
   - Forwarder `cac-moodle-fwd` (socat, 192.168.96.10:8088 → moodle:80):
     necesario porque el hairpin NAT del host está roto (los contenedores no
     alcanzan los puertos publicados del propio host) y Moodle exige que el
     Host de la petición coincida con `wwwroot` (303 si no). El engine usa
     `MOODLE_CONNECT_URL` para conectar al forwarder con Host = wwwroot.

 * **Repositorio de contenidos**
 https://github.com/FPVirtual/contenidos-test
   - Sembrado 2026-11-06: `course.yml` (dwes) + book `ut03-mvc` v1.0.0
     (tag `book/ut03-mvc/v1.0.0`). Clon local de trabajo: `~/Proyectos/contenidos-test`.

 * **Módulo base para pruebas "Desarrollo Web en Entorno Servidor" de DAW**
   - De momento no existe curso DWES en el Moodle; hay `CAC-TEST` (id 2).

## Tareas

1. Instalar el plugin en Moodle y configurar. ✅ (2026-11-06, ver tasklist PRU)
2. Crear una estructura inicial para prueba de contenidos con un libro en el módulo Desarrollo Web en Entorno Servidor en DAW. ✅ (repo sembrado)
3. Establecer usuarios y roles. 🟡 (los datos los carga el equipo; rol técnico `courseascodesvc` ya completo)

Seguimiento detallado: [Tasklist — Pruebas alpha](Tasklist%20—%20Pruebas%20alpha.md)
