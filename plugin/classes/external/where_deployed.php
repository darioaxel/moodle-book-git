<?php
/**
 * where_deployed: consulta inversa — cursos con (source, content_id) en una
 * versión dada (ENG-079). 9ª función asumida (contrato functions.php).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

/**
 * Resuelve con SQL sobre la tabla: el despliegue ACTUAL de cada curso para la
 * clave (source, content_id) debe tener content_version = versión pedida.
 */
class where_deployed extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        return new \external_function_parameters([
            'source' => new \external_value(PARAM_TEXT, 'Fuente (repo/rama)'),
            'content_id' => new \external_value(PARAM_TEXT, 'Content id del Book'),
            'version' => new \external_value(PARAM_TEXT, 'Versión exacta (p. ej. 1.3.0)'),
        ]);
    }

    public static function execute(string $source, string $contentid, string $version): array {
        global $DB;
        $params = self::validate_parameters(self::execute_parameters(), [
            'source' => $source, 'content_id' => $contentid, 'version' => $version,
        ]);
        $context = \context_system::instance();
        self::validate_context($context);
        require_capability('local/courseascode:manage', $context);

        $rows = $DB->get_records_sql(
            'SELECT courseid, MAX(deployed_at) AS lastdeploy
               FROM {local_courseascode_deploy}
              WHERE source = :source AND content_id = :contentid
              GROUP BY courseid',
            ['source' => $params['source'], 'contentid' => $params['content_id']]
        );
        $courseids = [];
        foreach ($rows as $row) {
            $current = $DB->get_record_sql(
                'SELECT content_version FROM {local_courseascode_deploy}
                  WHERE courseid = :courseid AND source = :source AND content_id = :contentid
                  ORDER BY deployed_at DESC, id DESC FETCH FIRST 1 ROWS ONLY',
                ['courseid' => $row->courseid, 'source' => $params['source'], 'contentid' => $params['content_id']]
            );
            if ($current && $current->content_version === $params['version']) {
                $courseids[] = (int) $row->courseid;
            }
        }
        sort($courseids);
        return ['courseids' => $courseids];
    }

    public static function execute_returns(): \external_single_structure {
        return new \external_single_structure([
            'courseids' => new \external_multiple_structure(
                new \external_value(PARAM_INT, 'Course ID'),
                'Cursos cuyo despliegue actual es la versión pedida'
            ),
        ]);
    }
}
