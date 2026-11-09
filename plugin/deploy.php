<?php
// Acción de despliegue (§12.3 paso 4): POST /deploy del servicio (§17).

/**
 * Ejecuta el deploy confirmado desde la página de versión (bookversion.php).
 *
 * Solo POST con sesskey; exige `local/courseascode:deploy` +
 * `moodle/course:manageactivities` (§12.3, permisos de importación). El
 * pipeline completo (plan + ejecución idempotente, §17) lo corre el engine;
 * el plugin solo reenvía la petición y reporta el resultado.
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/lib.php');

$courseid = required_param('id', PARAM_INT);
$source = required_param('source', PARAM_TEXT);
$book = required_param('book', PARAM_TEXT);
$version = required_param('version', PARAM_TEXT);
$confirmdeletions = optional_param('confirmdeletions', 0, PARAM_BOOL);

require_login($courseid);
if (!data_submitted()) {
    // Solo POST con sesskey válido (data_submitted lo comprueba).
    throw new moodle_exception('invalidrequest', 'error');
}
$context = context_course::instance($courseid);
require_capability('local/courseascode:deploy', $context);
require_capability('moodle/course:manageactivities', $context);

$returnurl = new moodle_url('/local/courseascode/bookversion.php', [
    'id' => $courseid,
    'source' => $source,
    'book' => $book,
]);

try {
    $result = local_courseascode_service_post('/deploy', [
        'course_id' => $courseid,
        'source' => $source,
        'book_id' => $book,
        'version' => $version,
        'confirmed_deletions' => (bool) $confirmdeletions,
    ]);
} catch (moodle_exception $e) {
    // 409 RECALLED, 400 plan inválido, 502 Moodle…: mensaje accionable del engine.
    redirect($returnurl, $e->getMessage(), null, \core\output\notification::NOTIFY_ERROR);
}

if (empty($result->success)) {
    redirect($returnurl,
        get_string('deployfailed', 'local_courseascode', $result->message ?? ''),
        null, \core\output\notification::NOTIFY_ERROR);
}

$message = get_string('deploysuccess', 'local_courseascode', $result->version ?? $version);
foreach ($result->warnings ?? [] as $warning) {
    $message .= ' ⚠ ' . $warning;
}
redirect($returnurl, $message, null, \core\output\notification::NOTIFY_SUCCESS);
