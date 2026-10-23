<?php
// Panel de administración del curso (§23.1): estado de todos los Books.

/**
 * Panel del curso (esqueleto: consume GET /deployment/status del servicio).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/lib.php');

$courseid = required_param('id', PARAM_INT);
$context = context_course::instance($courseid);
require_login($courseid);
require_capability('local/courseascode:deploy', $context);

$PAGE->set_url(new moodle_url('/local/courseascode/admin.php', ['id' => $courseid]));
$PAGE->set_context($context);
$PAGE->set_title(get_string('admin', 'local_courseascode'));

echo $OUTPUT->header();

try {
    // §5.4: GET /deployment/status?course_id=.
    $data = local_courseascode_service_get('/deployment/status', ['course_id' => $courseid]);
    echo $OUTPUT->render_from_template('local_courseascode/admin', [
        'courseid' => $courseid,
        'books' => $data->books ?? [],
    ]);
} catch (moodle_exception $e) {
    echo $OUTPUT->notification($e->getMessage(), 'error');
}

echo $OUTPUT->footer();
