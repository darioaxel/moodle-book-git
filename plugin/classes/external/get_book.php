<?php
/**
 * get_book: estado actual del Book (metadatos, capítulos por stable id, assets).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

use local_courseascode\local\book_helper;

/**
 * Fuente de verdad del planner y de la detección de drift (§19.1): el
 * engine compara el objetivo con este estado y el content_hash con el
 * HTML actual de cada capítulo. 8ª función asumida (contrato functions.py).
 */
class get_book extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        return new \external_function_parameters([
            'bookid' => new \external_value(PARAM_INT, 'id de la instancia mod_book'),
        ]);
    }

    public static function execute(int $bookid): array {
        global $DB;
        $params = self::validate_parameters(self::execute_parameters(), ['bookid' => $bookid]);
        $book = book_helper::get_book_instance($params['bookid']);
        $context = \context_course::instance($book->course);
        self::validate_context($context);
        require_capability('local/courseascode:viewcatalog', $context);

        $cmid = book_helper::coursemodule_id($book->id);
        $numbering = array_search($book->numbering, [0 => 'none', 1 => 'numbers', 2 => 'bullets', 3 => 'indented']);

        $chapters = [];
        $mappings = $DB->get_records('local_courseascode_chapter', ['bookid' => $book->id]);
        foreach ($mappings as $mapping) {
            $chapter = $DB->get_record('book_chapters', ['id' => $mapping->chapterid]);
            if (!$chapter) {
                continue;
            }
            $chapters[] = [
                'stable_id' => $mapping->stable_id,
                'title' => $chapter->title,
                'content_html' => $chapter->content,
                'position' => (int) $chapter->pagenum,
                'url' => (new \moodle_url('/mod/book/view.php', ['id' => $cmid, 'chapterid' => $chapter->id]))->out(false),
            ];
        }
        usort($chapters, fn ($a, $b) => $a['position'] <=> $b['position']);

        $assets = [];
        $files = get_file_storage()->get_area_files(
            $context->id, 'local_courseascode', 'asset', $book->id, 'filename', false
        );
        foreach ($files as $file) {
            $assets[] = ['filename' => $file->get_filename(), 'sha256' => hash('sha256', $file->get_content())];
        }

        return [
            'bookid' => (int) $book->id,
            'courseid' => (int) $book->course,
            'name' => $book->name,
            'intro' => $book->intro,
            'numbering' => $numbering === false ? 'numbers' : (string) $numbering,
            'assets' => $assets,
            'chapters' => $chapters,
        ];
    }

    public static function execute_returns(): \external_single_structure {
        return new \external_single_structure([
            'bookid' => new \external_value(PARAM_INT, 'id de la instancia mod_book'),
            'courseid' => new \external_value(PARAM_INT, 'Curso Moodle'),
            'name' => new \external_value(PARAM_TEXT, 'Título del Book'),
            'intro' => new \external_value(PARAM_RAW, 'Introducción (HTML)'),
            'numbering' => new \external_value(PARAM_ALPHAEXT, 'none|numbers|bullets|indented'),
            'assets' => new \external_multiple_structure(new \external_single_structure([
                'filename' => new \external_value(PARAM_FILE, 'Nombre del asset'),
                'sha256' => new \external_value(PARAM_ALPHANUMEXT, 'SHA-256 del contenido'),
            ]), 'Assets del Book'),
            'chapters' => new \external_multiple_structure(new \external_single_structure([
                'stable_id' => new \external_value(PARAM_TEXT, 'id estable del capítulo'),
                'title' => new \external_value(PARAM_TEXT, 'Título'),
                'content_html' => new \external_value(PARAM_RAW, 'HTML actual (detección de drift §19.1)'),
                'position' => new \external_value(PARAM_INT, 'posición 1-based'),
                'url' => new \external_value(PARAM_URL, 'URL de vista del capítulo (enlaces internos §16)'),
            ]), 'Capítulos por stable id, en orden'),
        ]);
    }
}
