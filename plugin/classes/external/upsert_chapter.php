<?php
/**
 * upsert_chapter: crea o actualiza un capítulo por su stable id (§17.3).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

use local_courseascode\local\book_helper;

/**
 * Idempotente: repetir con el mismo stable id actualiza el mismo capítulo.
 */
class upsert_chapter extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        return new \external_function_parameters([
            'bookid' => new \external_value(PARAM_INT, 'id de la instancia mod_book'),
            'chapter_stable_id' => new \external_value(PARAM_TEXT, 'id estable del capítulo (book.yml)'),
            'title' => new \external_value(PARAM_TEXT, 'Título'),
            'content_html' => new \external_value(PARAM_RAW, 'HTML renderizado y sanitizado'),
            'position' => new \external_value(PARAM_INT, 'posición 1-based en el índice'),
        ]);
    }

    public static function execute(int $bookid, string $chapterstableid, string $title, string $contenthtml, int $position): array {
        $params = self::validate_parameters(self::execute_parameters(), [
            'bookid' => $bookid, 'chapter_stable_id' => $chapterstableid, 'title' => $title,
            'content_html' => $contenthtml, 'position' => $position,
        ]);
        $book = book_helper::get_book_instance($params['bookid']);
        $context = \context_course::instance($book->course);
        self::validate_context($context);
        require_capability('local/courseascode:deploy', $context);
        book_helper::upsert_chapter_record(
            $params['bookid'], $params['chapter_stable_id'], $params['title'],
            $params['content_html'], $params['position']
        );
        return [];
    }

    public static function execute_returns(): \external_single_structure {
        return new \external_single_structure([]);
    }
}
