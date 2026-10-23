<?php
/**
 * upload_asset: sube (o sobrescribe) un asset y devuelve su URL pluginfile.
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');

use local_courseascode\local\book_helper;

/**
 * El fichero vive en el área local_courseascode/asset con itemid = bookid;
 * re-subir el mismo filename sobrescribe (idempotente).
 */
class upload_asset extends \external_api {
    public static function execute_parameters(): \external_function_parameters {
        return new \external_function_parameters([
            'bookid' => new \external_value(PARAM_INT, 'id de la instancia mod_book'),
            'filename' => new \external_value(PARAM_FILE, 'nombre del asset (p. ej. mvc.svg)'),
            'data' => new \external_value(PARAM_TEXT, 'contenido binario en base64'),
        ]);
    }

    public static function execute(int $bookid, string $filename, string $data): array {
        $params = self::validate_parameters(self::execute_parameters(), [
            'bookid' => $bookid, 'filename' => $filename, 'data' => $data,
        ]);
        $book = book_helper::get_book_instance($params['bookid']);
        $context = \context_course::instance($book->course);
        self::validate_context($context);
        require_capability('local/courseascode:deploy', $context);

        $fs = get_file_storage();
        $filerecord = (object) [
            'contextid' => $context->id,
            'component' => 'local_courseascode',
            'filearea' => 'asset',
            'itemid' => $params['bookid'],
            'filepath' => '/',
            'filename' => $params['filename'],
        ];
        $existing = $fs->get_file(
            $context->id, 'local_courseascode', 'asset', $params['bookid'], '/', $params['filename']
        );
        if ($existing) {
            $existing->delete(); // Re-subir el mismo filename sobrescribe (idempotente).
        }
        $file = $fs->create_file_from_string($filerecord, base64_decode($params['data']));
        $url = \moodle_url::make_pluginfile_url(
            $file->get_contextid(), $file->get_component(), $file->get_filearea(),
            $file->get_itemid(), $file->get_filepath(), $file->get_filename()
        );
        return ['url' => $url->out(false)];
    }

    public static function execute_returns(): \external_single_structure {
        return new \external_single_structure([
            'url' => new \external_value(PARAM_URL, 'URL pluginfile.php definitiva'),
        ]);
    }
}
