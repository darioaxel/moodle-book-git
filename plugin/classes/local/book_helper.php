<?php
// Helpers compartidos de las funciones external.

/**
 * Book helper: instancia mod_book, mapping de capítulos y filas de deploy.
 *
 * El Book se almacena como instancia de mod_book; la correspondencia
 * stable id ↔ chapterid vive en local_courseascode_chapter (idempotencia §17.3)
 * y el binding curso↔versión en local_courseascode_deploy (§9).
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\local;

defined('MOODLE_INTERNAL') || die();

/**
 * Operaciones comunes sobre el Book gestionado por el engine.
 */
class book_helper {
    /** Mapa numbering texto → constante mod_book. */
    private const NUMBERING = ['none' => 0, 'numbers' => 1, 'bullets' => 2, 'indented' => 3];

    /**
     * Instancia mod_book por su id (la usa el engine como "bookid" opaco).
     */
    public static function get_book_instance(int $bookid): \stdClass {
        global $DB;
        $book = $DB->get_record('book', ['id' => $bookid]);
        if (!$book) {
            throw new \moodle_exception('book_not_found', 'local_courseascode');
        }
        return $book;
    }

    /**
     * Crea o actualiza la instancia mod_book del curso (idempotente por nombre).
     *
     * @return int id de la instancia mod_book (el "bookid" del contrato)
     */
    public static function upsert_book_instance(int $courseid, string $name, string $intro, string $numbering): int {
        global $DB, $CFG;
        require_once($CFG->dirroot . '/course/modlib.php');
        require_once($CFG->dirroot . '/mod/book/locallib.php');

        $book = $DB->get_record('book', ['course' => $courseid, 'name' => $name]);
        $data = (object) [
            'name' => $name,
            'intro' => $intro,
            'introformat' => FORMAT_HTML,
            'numbering' => self::NUMBERING[$numbering] ?? 1,
            'course' => $courseid,
            'module' => $DB->get_field('modules', 'id', ['name' => 'book'], MUST_EXIST),
            'modulename' => 'book',
            'section' => 0,
            'visible' => 1,
        ];
        if ($book) {
            $data->id = $book->id;
            $data->coursemodule = self::coursemodule_id($book->id);
            update_module($data);
            return $book->id;
        }
        $data->instance = '';
        $data->coursemodule = 0;
        $created = add_module($data);
        return (int) $created->instance;
    }

    /**
     * Capítulo de mod_book asociado a un stable id, o null.
     */
    public static function chapter_by_stable_id(int $bookid, string $stableid): ?\stdClass {
        global $DB;
        $mapping = $DB->get_record('local_courseascode_chapter', ['bookid' => $bookid, 'stable_id' => $stableid]);
        if (!$mapping) {
            return null;
        }
        return $DB->get_record('book_chapters', ['id' => $mapping->chapterid]) ?: null;
    }

    /**
     * Crea o actualiza el capítulo de un stable id y devuelve el registro.
     */
    public static function upsert_chapter_record(int $bookid, string $stableid, string $title, string $html, int $position): \stdClass {
        global $DB;
        $chapter = self::chapter_by_stable_id($bookid, $stableid);
        $data = (object) [
            'bookid' => $bookid,
            'title' => $title,
            'content' => $html,
            'contentformat' => FORMAT_HTML,
            'pagenum' => $position,
            'hidden' => 0,
        ];
        if ($chapter) {
            $data->id = $chapter->id;
            $DB->update_record('book_chapters', $data);
            return $DB->get_record('book_chapters', ['id' => $chapter->id], '*', MUST_EXIST);
        }
        $chapterid = (int) $DB->insert_record('book_chapters', $data);
        $DB->insert_record('local_courseascode_chapter', (object) ['bookid' => $bookid, 'stable_id' => $stableid, 'chapterid' => $chapterid]);
        return $DB->get_record('book_chapters', ['id' => $chapterid], '*', MUST_EXIST);
    }

    /**
     * Elimina el capítulo de un stable id (mapping + chapter). Error si no existe.
     */
    public static function delete_chapter_record(int $bookid, string $stableid): void {
        global $DB;
        $mapping = $DB->get_record('local_courseascode_chapter', ['bookid' => $bookid, 'stable_id' => $stableid]);
        if (!$mapping) {
            throw new \moodle_exception('chapter_not_found', 'local_courseascode');
        }
        $DB->delete_records('book_chapters', ['id' => $mapping->chapterid]);
        $DB->delete_records('local_courseascode_chapter', ['id' => $mapping->id]);
    }

    /**
     * coursemodule id de una instancia mod_book.
     */
    public static function coursemodule_id(int $bookid): int {
        global $DB;
        return (int) $DB->get_field('course_modules', 'id', ['instance' => $bookid, 'module' => $DB->get_field('modules', 'id', ['name' => 'book'])], MUST_EXIST);
    }

    /**
     * Fila de deploy formateada para el contrato (deployed_at en ISO 8601).
     *
     * @param \stdClass|null $row
     * @return array<string, mixed>|null
     */
    public static function deploy_row(?\stdClass $row): ?array {
        if (!$row) {
            return null;
        }
        return [
            'id' => (int) $row->id,
            'courseid' => (int) $row->courseid,
            'bookid' => (int) $row->bookid,
            'source' => $row->source,
            'content_id' => $row->content_id,
            'content_version' => $row->content_version,
            'git_ref' => $row->git_ref,
            'git_commit' => $row->git_commit,
            'content_hash' => $row->content_hash,
            'deployed_at' => gmdate('c', (int) $row->deployed_at),
            'deployed_by' => $row->deployed_by,
            'status' => $row->status,
        ];
    }

    /**
     * Estructura external de una fila de deploy (single structure nullable).
     */
    public static function deploy_structure(): \external_single_structure {
        return new \external_single_structure([
            'id' => new \external_value(PARAM_INT, 'ID del registro'),
            'courseid' => new \external_value(PARAM_INT, 'Curso Moodle'),
            'bookid' => new \external_value(PARAM_INT, 'id de la instancia mod_book'),
            'source' => new \external_value(PARAM_TEXT, 'Fuente (repo/rama)'),
            'content_id' => new \external_value(PARAM_TEXT, 'Content id del Book'),
            'content_version' => new \external_value(PARAM_TEXT, 'Versión desplegada'),
            'git_ref' => new \external_value(PARAM_TEXT, 'Tag/rama/commit'),
            'git_commit' => new \external_value(PARAM_TEXT, 'SHA del commit'),
            'content_hash' => new \external_value(PARAM_RAW, 'JSON {stable_id: sha256}'),
            'deployed_at' => new \external_value(PARAM_TEXT, 'ISO 8601'),
            'deployed_by' => new \external_value(PARAM_TEXT, 'Quién desplegó'),
            'status' => new \external_value(PARAM_ALPHA, 'ok | error'),
        ]);
    }
}
