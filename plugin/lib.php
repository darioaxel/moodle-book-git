<?php
// Librería del plugin: cliente del servicio (server-to-server) e inyección CSS.

/**
 * Library functions.
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * URL base del servicio courseascode (configuración obligatoria en producción).
 */
function local_courseascode_service_url(): string {
    global $CFG;
    if (empty($CFG->local_courseascode_service_url)) {
        throw new \moodle_exception('servicenotconfigured', 'local_courseascode');
    }
    return rtrim($CFG->local_courseascode_service_url, '/');
}

/**
 * GET server-to-server contra la API del servicio (§5.4) con el token
 * configurado. Devuelve el body decodificado.
 *
 * @param array<string, string> $query
 * @return mixed
 */
function local_courseascode_service_get(string $path, array $query = []) {
    global $CFG;
    $url = local_courseascode_service_url() . $path . ($query ? '?' . http_build_query($query) : '');
    $curl = new \curl();
    $response = $curl->get($url, [], [
        'CURLOPT_HTTPHEADER' => ['X-CourseAsCode-User: ' . ($CFG->local_courseascode_service_token ?? '')],
    ]);
    if ($curl->get_errno()) {
        throw new \moodle_exception('servicerror', 'local_courseascode', '', $curl->error);
    }
    $data = json_decode($response);
    if ($data === null) {
        throw new \moodle_exception('servicerror', 'local_courseascode', '', 'invalid JSON');
    }
    return $data;
}

/**
 * Inyección del CSS del tema en las páginas del Book (§5.3d).
 * El CSS lo sirve el engine como asset temático; aquí solo se enlaza.
 */
function local_courseascode_before_standard_html_head(): string {
    global $PAGE;
    if ($PAGE->pagetype !== 'mod-book-view') {
        return '';
    }
    try {
        return \html_writer::tag('link', '', [
            'rel' => 'stylesheet',
            'href' => local_courseascode_service_url() . '/static/theme-default.css',
        ]);
    } catch (\moodle_exception $e) {
        return ''; // Servicio no configurado: el campus sigue funcionando.
    }
}

/**
 * Navegación: entrada "Course as Code" en el bloque de administración del curso.
 */
function local_courseascode_extend_navigation_course(\navigation_node $parent, \stdClass $course, \context_course $context): void {
    if (has_capability('local/courseascode:viewcatalog', $context)) {
        $parent->add(
            get_string('pluginname', 'local_courseascode'),
            new \moodle_url('/local/courseascode/catalog.php', ['id' => $course->id]),
            navigation_node::TYPE_SETTING,
            null,
            'local_courseascode',
            new \pix_icon('i/book', '')
        );
    }
}
