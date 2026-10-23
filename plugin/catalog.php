<?php
// Catálogo del curso (§12.2): Curso → Course as Code → Catálogo.

/**
 * Catálogo de Books importables (esqueleto: consume GET /catalog del servicio).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/lib.php');

$courseid = required_param('id', PARAM_INT);
$context = context_course::instance($courseid);
require_login($courseid);
require_capability('local/courseascode:viewcatalog', $context);

$PAGE->set_url(new moodle_url('/local/courseascode/catalog.php', ['id' => $courseid]));
$PAGE->set_context($context);
$PAGE->set_title(get_string('catalog', 'local_courseascode'));
$PAGE->set_heading(format_string($context->get_course()->fullname));

echo $OUTPUT->header();

try {
    // §5.4: GET /catalog con la identidad del llamante (ACL de fuentes).
    $data = local_courseascode_service_get('/catalog');
    echo $OUTPUT->render_from_template('local_courseascode/catalog', [
        'courseid' => $courseid,
        'sources' => $data->sources ?? [],
    ]);
} catch (moodle_exception $e) {
    echo $OUTPUT->notification($e->getMessage(), 'error');
}

echo $OUTPUT->footer();
