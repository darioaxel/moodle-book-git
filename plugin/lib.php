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
 * Petición server-to-server contra la API del servicio (§5.4).
 *
 * Comprueba el status HTTP: las respuestas de error del engine son JSON
 * ``{"detail": ...}`` (HTTPException de FastAPI) y se convierten en
 * ``moodle_exception`` accionable.
 *
 * @param string $method GET | POST
 * @param array<string, string> $query
 * @param array<string, mixed>|null $payload body JSON (solo POST)
 * @return mixed body decodificado
 */
function local_courseascode_service_request(string $method, string $path, array $query = [], ?array $payload = null) {
    global $CFG;
    $url = local_courseascode_service_url() . $path . ($query ? '?' . http_build_query($query) : '');
    $headers = [
        'X-CourseAsCode-User: ' . ($CFG->local_courseascode_service_token ?? ''),
        'Accept: application/json',
    ];
    $curl = new \curl();
    if ($method === 'POST') {
        $headers[] = 'Content-Type: application/json';
        $response = $curl->post($url, json_encode($payload ?? []), ['CURLOPT_HTTPHEADER' => $headers]);
    } else {
        $response = $curl->get($url, [], ['CURLOPT_HTTPHEADER' => $headers]);
    }
    if ($curl->get_errno()) {
        throw new \moodle_exception('servicerror', 'local_courseascode', '', $curl->error);
    }
    $status = (int) ($curl->get_info()['http_code'] ?? 0);
    $data = json_decode($response);
    if ($status >= 400) {
        $detail = (is_object($data) && !empty($data->detail)) ? $data->detail : "HTTP {$status}";
        throw new \moodle_exception('servicerror', 'local_courseascode', '', $detail);
    }
    if ($data === null) {
        throw new \moodle_exception('servicerror', 'local_courseascode', '', 'invalid JSON');
    }
    return $data;
}

/**
 * GET server-to-server contra la API del servicio (§5.4).
 *
 * @param array<string, string> $query
 * @return mixed
 */
function local_courseascode_service_get(string $path, array $query = []) {
    return local_courseascode_service_request('GET', $path, $query);
}

/**
 * POST server-to-server contra la API del servicio (deploy/plan, §12.3, §17).
 *
 * @param array<string, mixed> $payload
 * @return mixed
 */
function local_courseascode_service_post(string $path, array $payload) {
    return local_courseascode_service_request('POST', $path, [], $payload);
}

/**
 * URL pública del servicio (para enlaces que abre el navegador del usuario:
 * preview, CSS). Si no se define, se usa la URL server-to-server.
 */
function local_courseascode_service_public_url(): string {
    global $CFG;
    if (!empty($CFG->local_courseascode_service_public_url)) {
        return rtrim($CFG->local_courseascode_service_public_url, '/');
    }
    return local_courseascode_service_url();
}

/**
 * URL de la preview pública del servicio (ENG-044): mismo renderer que el deploy.
 * La abre el navegador del profesor: usa la URL pública del servicio.
 */
function local_courseascode_preview_url(string $source, string $book, ?string $ref = null): string {
    $url = local_courseascode_service_public_url() . "/catalog/{$source}/{$book}/preview";
    return $ref ? $url . '?ref=' . rawurlencode($ref) : $url;
}

/**
 * Último despliegue registrado en el curso por cada Book (binding §9).
 *
 * @return \stdClass[] filas de local_courseascode_deploy (la más reciente por source+content_id)
 */
function local_courseascode_course_deploys(int $courseid): array {
    global $DB;
    $rows = $DB->get_records('local_courseascode_deploy', ['courseid' => $courseid], 'deployed_at DESC, id DESC');
    $latest = [];
    foreach ($rows as $row) {
        $key = $row->source . '/' . $row->content_id;
        if (!isset($latest[$key])) {
            $latest[$key] = $row;
        }
    }
    return array_values($latest);
}

/**
 * Estado §19 de un Book en el curso, tolerante a fallos: si el servicio no
 * puede calcularlo devuelve un objeto ERROR con el detalle (la tabla del
 * panel debe seguir mostrando el resto de Books).
 */
function local_courseascode_book_state(int $courseid, string $source, string $book): \stdClass {
    try {
        return local_courseascode_service_get('/deployment/status', [
            'course_id' => (string) $courseid,
            'source' => $source,
            'book_id' => $book,
        ]);
    } catch (\moodle_exception $e) {
        return (object) [
            'state' => 'ERROR',
            'severity' => null,
            'version' => null,
            'git_commit' => '',
            'detail' => $e->getMessage(),
        ];
    }
}

/**
 * Etiqueta traducida de un DeploymentState (§19) para la UI.
 */
function local_courseascode_state_label(string $state): string {
    $key = 'state_' . strtolower($state);
    return get_string_manager()->string_exists($key, 'local_courseascode')
        ? get_string($key, 'local_courseascode')
        : $state;
}

/**
 * Clase Bootstrap del badge/alerta de un estado (§19) con su severidad (§11).
 */
function local_courseascode_state_class(string $state, ?string $severity = null): string {
    if ($severity === 'critical') {
        return 'danger';
    }
    return match ($state) {
        'UP_TO_DATE' => 'success',
        'UPDATE_AVAILABLE' => 'warning',
        'DRIFT_DETECTED', 'ERROR' => 'danger',
        'DEPLOYING' => 'info',
        default => 'secondary',
    };
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
            'href' => local_courseascode_service_public_url() . '/static/theme-default.css',
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
    if (has_capability('local/courseascode:deploy', $context)) {
        $node = $parent->get('local_courseascode') ?: $parent;
        $node->add(
            get_string('admin', 'local_courseascode'),
            new \moodle_url('/local/courseascode/admin.php', ['id' => $course->id]),
            navigation_node::TYPE_SETTING,
            null,
            'local_courseascode_admin',
            new \pix_icon('i/settings', '')
        );
    }
}
