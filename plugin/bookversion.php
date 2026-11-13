<?php
// Página de versión de un Book (§21, solo profesores): estado, versiones,
// cambios (§22, vía POST /deployment/plan) y confirmación de deploy (§17).

/**
 * Página de versión del Book.
 *
 * - Estado §19 del despliegue en este curso (badge con severidad §11).
 * - Metadata Git solo para profesores (capability viewcatalog; §21 privacidad).
 * - Lista de versiones taggeadas con Preview (ENG-044) y "Ver cambios".
 * - "Ver cambios" muestra el plan §17.1 (POST /deployment/plan): diff
 *   estructural §22, avisos y eliminaciones, con el formulario de
 *   confirmación que dispara el deploy real en deploy.php (§12.3 paso 4).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/lib.php');

$courseid = required_param('id', PARAM_INT);
$source = required_param('source', PARAM_TEXT);
$book = required_param('book', PARAM_TEXT);
$planversion = optional_param('plan', '', PARAM_TEXT);
$context = context_course::instance($courseid);
require_login($courseid);
require_capability('local/courseascode:viewcatalog', $context);

$pageurl = new moodle_url('/local/courseascode/bookversion.php',
    ['id' => $courseid, 'source' => $source, 'book' => $book]);
$PAGE->set_url($pageurl);
$PAGE->set_context($context);
$PAGE->set_title(get_string('bookversion', 'local_courseascode'));
$PAGE->set_heading(format_string(get_course($courseid)->fullname));

$candeploy = has_capability('local/courseascode:deploy', $context)
    && has_capability('moodle/course:manageactivities', $context);

echo $OUTPUT->header();

try {
    // §5.4: versiones disponibles y estado §19 del despliegue en este curso.
    $entry = local_courseascode_service_get("/catalog/{$source}/{$book}/versions");
    $status = local_courseascode_book_state($courseid, $source, $book);

    // Binding local: último despliegue registrado por el plugin (§9, §21).
    $deploy = null;
    foreach (local_courseascode_course_deploys($courseid) as $row) {
        if ($row->source === $source && $row->content_id === $book) {
            $deploy = $row;
            break;
        }
    }

    // Versiones en orden descendente (la más reciente primero, §21).
    $versions = array_reverse(array_map(function ($v) use ($courseid, $source, $book, $status, $pageurl) {
        return [
            'version' => $v->version,
            'tag' => $v->tag,
            'iscurrent' => ($status->version ?? null) === $v->version,
            'previewurl' => local_courseascode_preview_url($source, $book, $v->tag),
            'planurl' => (new moodle_url($pageurl, ['plan' => $v->version]))->out(false) . '#plan',
        ];
    }, $entry->versions ?? []));

    // Plan §17.1 de la versión candidata (diff estructural §22 + confirmación).
    $plan = null;
    if ($planversion !== '') {
        try {
            $raw = local_courseascode_service_post('/deployment/plan', [
                'course_id' => $courseid,
                'source' => $source,
                'book_id' => $book,
                'version' => $planversion,
            ]);
            $deletions = array_values(array_map(
                fn($a) => ['stable_id' => $a->stable_id ?? '', 'title' => $a->title ?? ''],
                array_filter($raw->actions ?? [], fn($a) => ($a->kind ?? '') === 'DELETE')
            ));
            $plan = [
                'version' => $planversion,
                'current' => $raw->current_version ?? '—',
                'target' => $raw->target_version ?? $planversion,
                'changes' => array_map(fn($c) => ['change' => $c], $raw->changes ?? []),
                'haschanges' => !empty($raw->changes),
                'warnings' => array_map(fn($w) => ['warning' => $w], $raw->warnings ?? []),
                'haswarnings' => !empty($raw->warnings),
                'deletions' => $deletions,
                'hasdeletions' => !empty($deletions),
                'deployurl' => (new moodle_url('/local/courseascode/deploy.php'))->out(false),
                'courseid' => $courseid,
                'source' => $source,
                'book' => $book,
                'sesskey' => sesskey(),
            ];
        } catch (moodle_exception $e) {
            // P. ej. 409: versión RECALLED (§11) — la gestiona el coordinador.
            echo $OUTPUT->notification($e->getMessage(), 'error');
        }
    }

    echo $OUTPUT->render_from_template('local_courseascode/bookversion', [
        'title' => $entry->title ?? $book,
        'contentid' => '@' . $source . '/' . $book,
        'catalogurl' => (new moodle_url('/local/courseascode/catalog.php', ['id' => $courseid]))->out(false),
        'adminurl' => (new moodle_url('/local/courseascode/admin.php', ['id' => $courseid]))->out(false),
        'hasstatus' => true,
        'statelabel' => local_courseascode_state_label($status->state ?? 'ERROR'),
        'stateclass' => local_courseascode_state_class($status->state ?? '', $status->severity ?? null),
        'severity' => $status->severity ?? null,
        'iscritical' => ($status->severity ?? null) === 'critical',
        'statedetail' => $status->detail ?? '',
        'hasdeploy' => $deploy !== null,
        'deployedversion' => $deploy->content_version ?? '',
        'gitcommit' => $deploy ? substr($deploy->git_commit, 0, 8) : '',
        'deployedat' => $deploy ? userdate($deploy->deployed_at) : '',
        'deployedby' => $deploy->deployed_by ?? '',
        'latest' => $entry->latest ?? '',
        'versions' => $versions,
        'hasversions' => !empty($versions),
        'candeploy' => $candeploy,
        'plan' => $plan,
    ]);
} catch (moodle_exception $e) {
    echo $OUTPUT->notification($e->getMessage(), 'error');
}

echo $OUTPUT->footer();
