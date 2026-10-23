<?php
// Página de versión de un Book (§21, solo profesores): versiones, Preview,
// Compare y Deploy — esqueleto; el Deploy completo es POST /deploy (§12.3).

/**
 * Página de versión del Book.
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/lib.php');

$courseid = required_param('id', PARAM_INT);
$source = required_param('source', PARAM_TEXT);
$book = required_param('book', PARAM_TEXT);
$context = context_course::instance($courseid);
require_login($courseid);
require_capability('local/courseascode:viewcatalog', $context);

$PAGE->set_url(new moodle_url('/local/courseascode/bookversion.php',
    ['id' => $courseid, 'source' => $source, 'book' => $book]));
$PAGE->set_context($context);
$PAGE->set_title(get_string('bookversion', 'local_courseascode'));

echo $OUTPUT->header();

try {
    // §5.4: GET /catalog/{source}/{book}/versions.
    $data = local_courseascode_service_get("/catalog/{$source}/{$book}/versions");
    echo $OUTPUT->render_from_template('local_courseascode/bookversion', [
        'courseid' => $courseid, 'source' => $source, 'book' => $book,
        'versions' => $data->versions ?? [],
        'candeploy' => has_capability('local/courseascode:deploy', $context),
    ]);
} catch (moodle_exception $e) {
    echo $OUTPUT->notification($e->getMessage(), 'error');
}

echo $OUTPUT->footer();
