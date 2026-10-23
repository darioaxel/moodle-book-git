<?php
/**
 * register_deploy: inserta una fila en local_courseascode_deploy (append-only).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

use local_courseascode\local\book_helper;

/**
 * No actualiza filas previas: el historial queda intacto (contrato).
 */
class register_deploy extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        $row = book_helper::deploy_structure();
        $fields = [];
        foreach ($row->keys as $name => $value) {
            if ($name !== 'id') {
                $fields[$name] = $value;
            }
        }
        return new \external_function_parameters($fields);
    }

    public static function execute(
        int $courseid, int $bookid, string $source, string $contentid, string $contentversion,
        string $gitref, string $gitcommit, string $contenthash, string $deployedat, string $deployedby,
        string $status = 'ok'
    ): array {
        global $DB;
        $params = self::validate_parameters(self::execute_parameters(), [
            'courseid' => $courseid, 'bookid' => $bookid, 'source' => $source,
            'content_id' => $contentid, 'content_version' => $contentversion,
            'git_ref' => $gitref, 'git_commit' => $gitcommit, 'content_hash' => $contenthash,
            'deployed_at' => $deployedat, 'deployed_by' => $deployedby, 'status' => $status,
        ]);
        $context = \context_course::instance($params['courseid']);
        self::validate_context($context);
        require_capability('local/courseascode:deploy', $context);

        $timestamp = strtotime($params['deployed_at']);
        if ($timestamp === false) {
            throw new \moodle_exception('invalid_deployed_at', 'local_courseascode');
        }
        $id = (int) $DB->insert_record('local_courseascode_deploy', (object) [
            'courseid' => $params['courseid'],
            'bookid' => $params['bookid'],
            'source' => $params['source'],
            'content_id' => $params['content_id'],
            'content_version' => $params['content_version'],
            'git_ref' => $params['git_ref'],
            'git_commit' => $params['git_commit'],
            'content_hash' => $params['content_hash'],
            'deployed_at' => $timestamp,
            'deployed_by' => $params['deployed_by'],
            'status' => $params['status'],
        ]);
        return ['id' => $id];
    }

    public static function execute_returns(): \external_single_structure {
        return new \external_single_structure([
            'id' => new \external_value(PARAM_INT, 'ID de la fila insertada'),
        ]);
    }
}
