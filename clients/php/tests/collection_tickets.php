<?php
require dirname(__DIR__) . '/src/CollectionTickets.php';

use Porter\Client\CollectionTickets;

$root = sys_get_temp_dir() . '/porter-php-' . bin2hex(random_bytes(8));
mkdir($root, 0777, true);
$client = new CollectionTickets($root, 'sender');
$ticket = $client->deposit('recipient', 'demo.work', ['opaque' => true], 30);
assert(str_starts_with($ticket['ticket'], 'CT-'));
assert(str_starts_with($ticket['lodgement'], 'LG-'));
assert(is_file($root . '/lodgements/lodged/' . $ticket['lodgement'] . '.json'));
assert($client->inspect($ticket['ticket'])['state'] === 'OUTSTANDING');
$packagePath = $root . '/outgoing/' . $ticket['package'] . '.json';
unlink($root . '/tickets/' . $ticket['ticket'] . '.json');
unlink($root . '/tickets/by-package/' . $ticket['package']);
unlink($packagePath);
$client = new CollectionTickets($root, 'sender');
assert($client->resolveLodgement($ticket['lodgement'])['state'] === 'DEFINITELY_LODGED');
assert(is_file($packagePath));
$returnId = 'PKG-' . bin2hex(random_bytes(16));
$return = ['protocol' => 'PORTER/1', 'package' => $returnId, 'from' => 'recipient', 'to' => 'sender', 'kind' => 'porter.return', 'created' => time(), 'expires' => time() + 30, 'in_reply_to' => $ticket['package'], 'payload' => ['answer' => 42]];
file_put_contents($root . '/inbox/' . $returnId . '.json', json_encode($return));
assert($client->inspect($ticket['ticket'])['state'] === 'RETURN_HELD');
$round = $client->makeRound([$ticket['ticket']]);
assert($round['vocabulary'] === 'PORTER-ROUNDS/1');
assert(str_starts_with($round['round'], 'RD-'));
assert($round['initiated_by'] === 'sender');
assert($round['observations'][0]['state'] === 'RETURN_HELD');
assert(is_file($root . '/rounds/' . $round['round'] . '.json'));
assert(is_file($root . '/inbox/' . $returnId . '.json'), 'A Round must not collect');
$collected = $client->collect($ticket['ticket']);
assert($collected['state'] === 'COLLECTED');
assert($client->collect($ticket['ticket'])['state'] === 'ALREADY_COLLECTED');
$abandoned = $client->deposit('recipient', 'demo.work', [], 30);
assert($client->abandon($abandoned['ticket'])['state'] === 'ABANDONED');
echo "PORTER PHP Collection Ticket checks passed\n";
