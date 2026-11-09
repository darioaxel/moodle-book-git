<?php
// Strings del plugin (convención Moodle: inglés).

/**
 * Language strings.
 *
 * @package    local_courseascode
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

$string['pluginname'] = 'Course as Code';
$string['catalog'] = 'Catalog';
$string['bookversion'] = 'Book version';
$string['admin'] = 'Course as Code administration';
$string['courseascode:viewcatalog'] = 'View the Course as Code catalog';
$string['courseascode:deploy'] = 'Deploy and update Course as Code books';
$string['courseascode:manage'] = 'Manage Course as Code (system-wide)';
$string['book_not_found'] = 'The book does not exist';
$string['chapter_not_found'] = 'The chapter stable id does not exist in this book';
$string['invalid_course'] = 'The course does not exist';
$string['invalid_deployed_at'] = 'deployed_at is not a valid ISO 8601 datetime';
$string['privacy:metadata:reason'] = 'The plugin stores deployment metadata only; personal data is managed by the courseascode service audit log.';
$string['preview'] = 'Preview';
$string['addtocourse'] = 'Add to course';
$string['chaptercount'] = 'Chapters';
$string['latest'] = 'Latest version';
$string['version'] = 'Version';
$string['versions'] = 'Versions';
$string['servicenotconfigured'] = 'The courseascode service is not configured. Set $CFG->local_courseascode_service_url (see README).';
$string['servicerror'] = 'The courseascode service returned an error: {$a}';

// Catalog page (§12.2).
$string['catalogempty'] = 'There are no sources visible for you in the catalog.';
$string['nobooksinsource'] = 'This source has no released books yet.';

// Book version page (§21) and plan (§17.1, §22).
$string['content'] = 'Content';
$string['publishedversion'] = 'Published version';
$string['availableversion'] = 'Available';
$string['gitcommit'] = 'Git commit';
$string['publishedat'] = 'Published';
$string['deployedby'] = 'Deployed by';
$string['deployed'] = 'Deployed';
$string['deploy'] = 'Deploy';
$string['update'] = 'Update';
$string['changes'] = 'Changes';
$string['nochanges'] = 'No content changes: the deployment is already up to date.';
$string['viewchanges'] = 'View changes';
$string['critical'] = 'CRITICAL';
$string['deletionswarning'] = 'This deployment will delete the following chapters from the Moodle book:';
$string['confirmdeletions'] = 'I understand that those chapters will be permanently deleted from this course.';
$string['deploysuccess'] = 'Version {$a} deployed successfully.';
$string['deployfailed'] = 'The deployment failed: {$a}';
$string['noversions'] = 'This book has no tagged versions.';

// Course panel (§23.1).
$string['state'] = 'State';
$string['actions'] = 'Actions';
$string['viewincourse'] = 'View in course';
$string['nobooksdeployed'] = 'This course has no Course as Code books yet.';
$string['gotocatalog'] = 'Go to the catalog';

// Deployment states (§19).
$string['state_not_deployed'] = 'Not deployed';
$string['state_up_to_date'] = 'Up to date';
$string['state_update_available'] = 'Update available';
$string['state_drift_detected'] = 'Manual changes detected';
$string['state_deploying'] = 'Deploying';
$string['state_error'] = 'Error';
