<?php
/**
 * list_deploys: todos los despliegues de un curso (más reciente primero).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

use local_courseascode\local\book_helper;

/**
 * Asunción documentada en engine/src/courseascode/moodle/functions.py
 * (función 7ª, necesaria para ENG-060).
 */
class list_deploys extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        return new \external_function_parameters([
            'courseid' => new \external_value(PARAM_INT, 'Course ID'),
        ]);
    }

    public static function execute(int $courseid): array {
        global $DB;
        $params = self::validate_parameters(self::execute_parameters(), ['courseid' => $courseid]);
        $context = \context_course::instance($params['courseid']);
        self::validate_context($context);
        require_capability('local/courseascode:viewcatalog', $context);

        $rows = $DB->get_records('local_courseascode_deploy', ['courseid' => $params['courseid']], 'deployed_at DESC, id DESC');
        return ['deploys' => array_values(array_map(
            fn ($row) => (object) book_helper::deploy_row($row),
            $rows
        ))];
    }

    public static function execute_returns(): \external_single_structure {
        return new \external_single_structure([
            'deploys' => new \external_multiple_structure(book_helper::deploy_structure(), 'Despliegues del curso'),
        ]);
    }
}
