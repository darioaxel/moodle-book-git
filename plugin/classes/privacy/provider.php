<?php
// Privacy API (Moodle exige provider para plugins con datos).
// Las tablas guardan identificadores de despliegue (deployed_by = username
// opcional). Esqueleto: null provider; pendiente export real (post-Beta).

/**
 * Privacy provider.
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace local_courseascode\privacy;

defined('MOODLE_INTERNAL') || die();

/**
 * Sin datos personales exportables en esta versión (deployed_by es un
 * identificador operativo a cargo del servicio; ver auditoría del engine).
 */
class provider implements \core_privacy\local\metadata\null_provider {
    public static function get_reason(): string {
        return 'privacy:metadata:reason';
    }
}
