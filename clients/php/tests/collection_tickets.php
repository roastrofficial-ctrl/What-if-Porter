<?php
require dirname(__DIR__) . '/src/CollectionTickets.php';

use Porter\Client\CollectionTickets;

$root = sys_get_temp_dir() . '/porter-php-' . bin2hex(random_bytes(8));
mkdir($root, 0777, true);
$client = new CollectionTickets($root, 'sender');
$ticket = $client->deposit('recipient', 'demo.work', ['opaque' => true], 30);
assert(str_starts_with($ticket['ticket'], 'CT-'));
assert($client->inspect($ticket['ticket'])['state'] === 'OUTSTANDING');
$returnId = 'PKG-' . bin2hex(random_bytes(16));
$return = ['protocol' => 'PORTER/1', 'package' => $returnId, 'from' => 'recipient', 'to' => 'sender', 'kind' => 'porter.return', 'created' => time(), 'expires' => time() + 30, 'in_reply_to' => $ticket['package'], 'payload' => ['answer' => 42]];
file_put_contents($root . '/inbox/' . $returnId . '.json', json_encode($return));
assert($client->inspect($ticket['ticket'])['state'] === 'RETURN_HELD');
$collected = $client->collect($ticket['ticket']);
assert($collected['state'] === 'COLLECTED');
assert($client->collect($ticket['ticket'])['state'] === 'ALREADY_COLLECTED');
$abandoned = $client->deposit('recipient', 'demo.work', [], 30);
assert($client->abandon($abandoned['ticket'])['state'] === 'ABANDONED');
echo "PORTER PHP Collection Ticket checks passed\n";
