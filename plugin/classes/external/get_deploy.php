<?php
/**
 * get_deploy: último despliegue de (courseid, source, content_id).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

use local_courseascode\local\book_helper;

/**
 * El más reciente por deployed_at; null si nunca se desplegó (contrato).
 */
class get_deploy extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        return new \external_function_parameters([
            'courseid' => new \external_value(PARAM_INT, 'Course ID'),
            'source' => new \external_value(PARAM_TEXT, 'Fuente (repo/rama)'),
            'content_id' => new \external_value(PARAM_TEXT, 'Content id del Book'),
        ]);
    }

    public static function execute(int $courseid, string $source, string $contentid): array {
        global $DB;
        $params = self::validate_parameters(self::execute_parameters(), [
            'courseid' => $courseid, 'source' => $source, 'content_id' => $contentid,
        ]);
        $context = \context_course::instance($params['courseid']);
        self::validate_context($context);
        require_capability('local/courseascode:viewcatalog', $context);

        $row = $DB->get_record_sql(
            'SELECT * FROM {local_courseascode_deploy}
              WHERE courseid = :courseid AND source = :source AND content_id = :contentid
              ORDER BY deployed_at DESC, id DESC FETCH FIRST 1 ROWS ONLY',
            ['courseid' => $params['courseid'], 'source' => $params['source'], 'contentid' => $params['content_id']]
        );
        // Contrato (rest_client.get_deploy): la fila va en el nivel raíz y,
        // si no hay despliegue, la respuesta serializa como null → None.
        return $row ? book_helper::deploy_row($row) : [];
    }

    public static function execute_returns(): \external_single_structure {
        $values = [];
        foreach (book_helper::deploy_structure()->keys as $name => $value) {
            $values[$name] = new \external_value($value->type, $value->desc, VALUE_OPTIONAL);
        }
        return new \external_single_structure($values);
    }
}
