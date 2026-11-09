<?php
// Panel de administración del curso (§23.1): estado de todos los Books.

/**
 * Panel del curso.
 *
 * Lista los Books con binding en este curso (tabla local_courseascode_deploy)
 * con su estado §19 calculado por el servicio (GET /deployment/status) y la
 * última versión disponible en el catálogo (§5.4). Acciones por Book:
 * ver en el curso, preview, página de versión (cambios/deploy/rollback, §21).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/lib.php');
require_once(__DIR__ . '/classes/local/book_helper.php');

use local_courseascode\local\book_helper;

$courseid = required_param('id', PARAM_INT);
$context = context_course::instance($courseid);
require_login($courseid);
require_capability('local/courseascode:deploy', $context);

$PAGE->set_url(new moodle_url('/local/courseascode/admin.php', ['id' => $courseid]));
$PAGE->set_context($context);
$PAGE->set_title(get_string('admin', 'local_courseascode'));
$PAGE->set_heading(format_string($context->get_course()->fullname));

echo $OUTPUT->header();
echo $OUTPUT->heading(get_string('admin', 'local_courseascode'));

$books = [];
foreach (local_courseascode_course_deploys($courseid) as $deploy) {
    $status = local_courseascode_book_state($courseid, $deploy->source, $deploy->content_id);

    // Última versión disponible en el catálogo (— si el servicio no responde).
    $latest = '—';
    try {
        $entry = local_courseascode_service_get(
            "/catalog/{$deploy->source}/{$deploy->content_id}/versions");
        $latest = $entry->latest ?? '—';
    } catch (moodle_exception $e) {
        debugging('courseascode admin: versions de ' . $deploy->content_id . ': ' . $e->getMessage());
    }

    // Enlace al Book en el curso; si se borró a mano (drift §19.1), no hay cm.
    $viewurl = '';
    try {
        $cmid = book_helper::coursemodule_id((int) $deploy->bookid);
        $viewurl = (new moodle_url('/mod/book/view.php', ['id' => $cmid]))->out(false);
    } catch (dml_exception $e) {
        $viewurl = '';
    }

    $state = $status->state ?? 'ERROR';
    $books[] = [
        'contentid' => '@' . $deploy->source . '/' . $deploy->content_id,
        'published' => $deploy->content_version,
        'available' => $latest,
        'statelabel' => local_courseascode_state_label($state),
        'stateclass' => local_courseascode_state_class($state, $status->severity ?? null),
        'iscritical' => ($status->severity ?? null) === 'critical',
        'statedetail' => $status->detail ?? '',
        'hasupdate' => $state === 'UPDATE_AVAILABLE',
        'viewurl' => $viewurl,
        'hasviewurl' => $viewurl !== '',
        'previewurl' => local_courseascode_preview_url(
            $deploy->source, $deploy->content_id, $deploy->git_ref),
        'versionurl' => (new moodle_url('/local/courseascode/bookversion.php', [
            'id' => $courseid,
            'source' => $deploy->source,
            'book' => $deploy->content_id,
        ]))->out(false),
        'updateurl' => (new moodle_url('/local/courseascode/bookversion.php', [
            'id' => $courseid,
            'source' => $deploy->source,
            'book' => $deploy->content_id,
            'plan' => $latest,
        ]))->out(false) . '#plan',
    ];
}

echo $OUTPUT->render_from_template('local_courseascode/admin', [
    'books' => $books,
    'hasbooks' => !empty($books),
    'catalogurl' => (new moodle_url('/local/courseascode/catalog.php', ['id' => $courseid]))->out(false),
]);

echo $OUTPUT->footer();
