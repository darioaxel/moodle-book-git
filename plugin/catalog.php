<?php
// Catálogo del curso (§12.2): Curso → Course as Code → Catálogo.

/**
 * Catálogo de Books importables: consume GET /catalog del servicio (§5.4).
 *
 * Cada tarjeta muestra título, resumen, tags, nº de capítulos y última
 * versión (solo versiones taggeadas, ENG-051), con Preview (mismo renderer
 * que el deploy, principio 5) y acceso a la página de versión para añadir
 * el Book al curso (§12.3).
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
echo $OUTPUT->heading(get_string('catalog', 'local_courseascode'));

try {
    // §5.4: GET /catalog con la identidad del llamante (ACL de fuentes).
    $data = local_courseascode_service_get('/catalog');
    $candeploy = has_capability('local/courseascode:deploy', $context)
        && has_capability('moodle/course:manageactivities', $context);
    $sources = [];
    foreach ($data->sources ?? [] as $source) {
        $books = [];
        foreach ($source->books ?? [] as $book) {
            $books[] = [
                'id' => $book->id,
                'title' => $book->title,
                'summary' => $book->summary ?? '',
                'tags' => array_map(fn($tag) => ['tag' => $tag], $book->tags ?? []),
                'hastags' => !empty($book->tags),
                'audience' => $book->audience ?? '',
                'chapter_count' => $book->chapter_count ?? 0,
                'latest' => $book->latest ?? '',
                'previewurl' => local_courseascode_preview_url($source->source, $book->id),
                'versionurl' => (new moodle_url('/local/courseascode/bookversion.php', [
                    'id' => $courseid,
                    'source' => $source->source,
                    'book' => $book->id,
                ]))->out(false),
            ];
        }
        $sources[] = [
            'name' => $source->source,
            'books' => $books,
            'hasbooks' => !empty($books),
        ];
    }
    echo $OUTPUT->render_from_template('local_courseascode/catalog', [
        'sources' => $sources,
        'hassources' => !empty($sources),
        'candeploy' => $candeploy,
    ]);
} catch (moodle_exception $e) {
    echo $OUTPUT->notification($e->getMessage(), 'error');
}

echo $OUTPUT->footer();
