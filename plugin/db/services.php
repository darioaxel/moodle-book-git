<?php
// Web services del plugin (contrato §5.3b — fuente de verdad cruzada con
// engine/src/courseascode/moodle/functions.py).

/**
 * Services definition.
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$functions = [
    'local_courseascode_upsert_book' => [
        'classname' => 'local_courseascode\\external\\upsert_book',
        'methodname' => 'execute',
        'description' => 'Crea o actualiza el Book del curso (idempotente).',
        'type' => 'write',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_upsert_chapter' => [
        'classname' => 'local_courseascode\\external\\upsert_chapter',
        'methodname' => 'execute',
        'description' => 'Crea o actualiza un capítulo por su stable id (idempotente).',
        'type' => 'write',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_delete_chapter' => [
        'classname' => 'local_courseascode\\external\\delete_chapter',
        'methodname' => 'execute',
        'description' => 'Elimina un capítulo por su stable id.',
        'type' => 'write',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_upload_asset' => [
        'classname' => 'local_courseascode\\external\\upload_asset',
        'methodname' => 'execute',
        'description' => 'Sube (o sobrescribe) un asset del Book; devuelve URL pluginfile.',
        'type' => 'write',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_register_deploy' => [
        'classname' => 'local_courseascode\\external\\register_deploy',
        'methodname' => 'execute',
        'description' => 'Registra un despliegue (historial append-only).',
        'type' => 'write',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_get_deploy' => [
        'classname' => 'local_courseascode\\external\\get_deploy',
        'methodname' => 'execute',
        'description' => 'Último despliegue de (courseid, source, content_id).',
        'type' => 'read',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_list_deploys' => [
        'classname' => 'local_courseascode\\external\\list_deploys',
        'methodname' => 'execute',
        'description' => 'Todos los despliegues de un curso.',
        'type' => 'read',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_get_book' => [
        'classname' => 'local_courseascode\\external\\get_book',
        'methodname' => 'execute',
        'description' => 'Estado actual del Book: metadatos, capítulos por stable id, assets.',
        'type' => 'read',
        'loginrequired' => true,
        'ajax' => false,
    ],
    'local_courseascode_where_deployed' => [
        'classname' => 'local_courseascode\\external\\where_deployed',
        'methodname' => 'execute',
        'description' => 'Consulta inversa: cursos con (source, content_id) en versión dada.',
        'type' => 'read',
        'loginrequired' => true,
        'ajax' => false,
    ],
];
