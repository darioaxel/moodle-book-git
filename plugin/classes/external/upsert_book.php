<?php
/**
 * upsert_book: crea o actualiza el Book del curso (idempotente).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

use local_courseascode\local\book_helper;

/**
 * Crea el Book (instancia mod_book) si no existe o actualiza nombre/intro/numbering.
 */
class upsert_book extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        return new \external_function_parameters([
            'courseid' => new \external_value(PARAM_INT, 'Course ID'),
            'name' => new \external_value(PARAM_TEXT, 'Título del Book'),
            'intro' => new \external_value(PARAM_RAW, 'Introducción (HTML)'),
            'numbering' => new \external_value(PARAM_ALPHAEXT, 'none|numbers|bullets|indented'),
        ]);
    }

    public static function execute(int $courseid, string $name, string $intro, string $numbering): array {
        $params = self::validate_parameters(self::execute_parameters(), [
            'courseid' => $courseid, 'name' => $name, 'intro' => $intro, 'numbering' => $numbering,
        ]);
        $context = \context_course::instance($params['courseid']);
        self::validate_context($context);
        require_capability('local/courseascode:deploy', $context);
        if (!get_fast_modinfo($params['courseid'])->get_course()) {
            throw new \moodle_exception('invalid_course', 'local_courseascode');
        }
        $bookid = book_helper::upsert_book_instance(
            $params['courseid'], $params['name'], $params['intro'], $params['numbering']
        );
        return ['bookid' => $bookid];
    }

    public static function execute_returns(): \external_single_structure {
        return new \external_single_structure([
            'bookid' => new \external_value(PARAM_INT, 'id de la instancia mod_book'),
        ]);
    }
}
