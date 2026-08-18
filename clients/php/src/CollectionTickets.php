<?php

namespace Porter\Client;

use RuntimeException;

final class CollectionTickets
{
    public function __construct(private readonly string $ipc, private readonly string $sender)
    {
        $this->recoverLodgements();
        $this->recoverCollections();
    }

    public function deposit(string $recipient, string $kind, array $payload, int $ttl = 300, ?string $inReplyTo = null): array
    {
        $now = time();
        $packageId = 'PKG-' . bin2hex(random_bytes(16));
        $ticketId = 'CT-' . bin2hex(random_bytes(16));
        $lodgementId = 'LG-' . bin2hex(random_bytes(16));
        $package = ['protocol' => 'PORTER/1', 'package' => $packageId, 'from' => $this->sender, 'to' => $recipient, 'kind' => $kind, 'created' => $now, 'expires' => $now + $ttl, 'reply_to' => $this->sender, 'payload' => $payload];
        if ($inReplyTo !== null) $package['in_reply_to'] = $inReplyTo;
        $lodgedAt = $this->now();
        $ticket = ['protocol' => 'PORTER/1', 'ticket' => $ticketId, 'package' => $packageId, 'lodgement' => $lodgementId, 'created' => $now, 'expires' => $now + $ttl, 'abandoned' => false, 'collected_return' => null, 'events' => [['event' => 'LODGED', 'at_ms' => $lodgedAt, 'details' => ['lodgement' => $lodgementId]]]];
        $lodgement = ['protocol' => 'PORTER/1', 'kind' => 'LODGEMENT', 'lodgement' => $lodgementId, 'state' => 'LODGED', 'lodged_at_ms' => $lodgedAt, 'ticket' => $ticket, 'package' => $package];
        foreach (['lodgements/lodged', 'lodgements/locks', 'tickets', 'tickets/by-package', 'outgoing', 'inbox', 'collected', 'receipts', 'refused'] as $folder) $this->folder($folder);
        // This atomic publication is the ceremony's one durable truth. Everything
        // below is a replay-safe materialisation of correspondence already lodged.
        $this->atomic("lodgements/lodged/{$lodgementId}.json", $lodgement);
        $this->materialize($lodgement);
        return $ticket;
    }

    public function recoverLodgements(): void
    {
        $this->folder('lodgements/lodged');
        foreach (glob($this->path('lodgements/lodged/LG-*.json')) ?: [] as $path) {
            $value = json_decode((string)file_get_contents($path), true);
            if (is_array($value)) $this->materialize($value);
        }
    }

    public function resolveLodgement(string $lodgementId): array
    {
        $path = $this->path("lodgements/lodged/{$lodgementId}.json");
        if (!is_file($path)) return ['lodgement' => $lodgementId, 'state' => 'NEVER_LODGED'];
        $value = json_decode((string)file_get_contents($path), true);
        if (!is_array($value)) throw new RuntimeException('Unreadable PORTER lodgement fact');
        $this->materialize($value);
        return ['lodgement' => $lodgementId, 'state' => 'DEFINITELY_LODGED', 'ticket' => $value['ticket']['ticket'], 'package' => $value['package']['package']];
    }

    public function inspect(string $ticketId, bool $record = true): array
    {
        $ticket = $this->readTicket($ticketId);
        $returns = [];
        foreach (glob($this->path('inbox/PKG-*.json')) ?: [] as $path) {
            $value = json_decode((string)file_get_contents($path), true);
            if (($value['in_reply_to'] ?? null) === $ticket['package']) $returns[] = $value['package'];
        }
        $collectedReturn = $ticket['collected_return'];
        if (!$collectedReturn) {
            foreach (glob($this->path('collections/facts/CL-*.json')) ?: [] as $path) {
                $fact = json_decode((string)file_get_contents($path), true);
                if (($fact['package']['in_reply_to'] ?? null) === $ticket['package']) {
                    $collectedReturn = $fact['package']['package'];
                    break;
                }
            }
        }
        if ($collectedReturn) $state = 'COLLECTED';
        elseif ($ticket['abandoned'] && $returns) $state = 'ABANDONED_WITH_RETURN';
        elseif ($ticket['abandoned']) $state = 'ABANDONED';
        elseif ($returns) $state = 'RETURN_HELD';
        elseif ($ticket['expires'] <= time()) $state = 'EXPIRED_OBSERVED';
        else $state = 'OUTSTANDING';
        $carriagePath = $this->path("carriage/{$ticket['package']}.json");
        $carriage = is_file($carriagePath) ? json_decode((string)file_get_contents($carriagePath), true) : ['knowledge' => 'NOT_YET_ATTEMPTED', 'attempts' => []];
        if ($record) $this->event($ticketId, 'TICKET_INSPECTED', ['observed_state' => $state, 'held_returns' => count($returns), 'carriage_knowledge' => $carriage['knowledge']]);
        $result = [...$ticket, 'collected_return' => $collectedReturn, 'state' => $state, 'held_returns' => $returns, 'duplicate_returns' => max(0, count($returns) - 1), 'carriage_knowledge' => $carriage['knowledge'], 'carriage_attempts' => count($carriage['attempts'])];
        if (isset($carriage['acceptance_evidence'])) $result['acceptance_evidence'] = $carriage['acceptance_evidence'];
        return $result;
    }

    public function makeRound(array $ticketIds): array
    {
        if ($ticketIds === []) throw new RuntimeException('A PORTER Round requires at least one Collection Ticket');
        $beganAt = $this->now();
        $snapshots = array_map(fn($ticketId) => $this->inspect((string)$ticketId), $ticketIds);
        $observedAt = $this->now();
        $roundId = 'RD-' . bin2hex(random_bytes(16));
        $observations = array_map(function (array $ticket) use ($observedAt) {
            $value = ['ticket' => $ticket['ticket'], 'package' => $ticket['package'], 'state' => $ticket['state'], 'held_returns' => $ticket['held_returns'], 'duplicate_returns' => $ticket['duplicate_returns'], 'carriage_knowledge' => $ticket['carriage_knowledge'], 'carriage_attempts' => $ticket['carriage_attempts']];
            if (isset($ticket['acceptance_evidence'])) $value['acceptance_evidence'] = $ticket['acceptance_evidence'];
            $heldAt = $this->eventAt($ticket, 'RETURN_HELD');
            if ($heldAt !== null) {
                $value['return_held_at_ms'] = $heldAt;
                $value['observation_latency_ms'] = max(0, $observedAt - $heldAt);
                $lodgedAt = $this->eventAt($ticket, 'LODGED');
                if ($lodgedAt !== null) {
                    $value['lodged_at_ms'] = $lodgedAt;
                    $value['carriage_latency_ms'] = max(0, $heldAt - $lodgedAt);
                }
            }
            return $value;
        }, $snapshots);
        $round = ['vocabulary' => 'PORTER-ROUNDS/1', 'round' => $roundId, 'initiated_by' => $this->sender, 'began_at_ms' => $beganAt, 'observed_at_ms' => $observedAt, 'observations' => $observations];
        $this->folder('rounds');
        $this->atomic("rounds/{$roundId}.json", $round);
        return $round;
    }

    public function collect(string $ticketId): array
    {
        $status = $this->inspect($ticketId, false);
        if ($status['collected_return']) {
            $fact = $this->collectPackage($status['collected_return']);
            return ['state' => 'ALREADY_COLLECTED', 'return' => $status['collected_return'], 'collection' => $fact['collection'], 'package' => $fact['package']];
        }
        if ($status['held_returns'] === []) return ['state' => $status['state'], 'package' => null];
        sort($status['held_returns']);
        $returnId = $status['held_returns'][0];
        $fact = $this->collectPackage($returnId);
        $this->mutate($ticketId, function (array $ticket) use ($returnId, $fact) {
            $ticket['collected_return'] = $returnId;
            $ticket['events'][] = ['event' => 'RETURN_COLLECTED', 'at_ms' => $this->now(), 'details' => ['return' => $returnId, 'collection' => $fact['collection']]];
            return $ticket;
        });
        return ['state' => $fact['state'], 'return' => $returnId, 'collection' => $fact['collection'], 'package' => $fact['package'], 'duplicates_retained' => max(0, count($status['held_returns']) - 1)];
    }

    /** Host-initiated transfer of one accepted Package into recoverable Host custody. */
    public function collectPackage(string $packageId): array
    {
        $this->folder('collections/locks');
        $lockPath = $this->path("collections/locks/{$packageId}.lock");
        $lock = fopen($lockPath, 'c+');
        if (!$lock || !flock($lock, LOCK_EX)) throw new RuntimeException('Could not begin PORTER Collection');
        @chmod($lockPath, 0666);
        try {
            $existing = $this->findCollection($packageId);
            if ($existing !== null) {
                $this->materializeCollection($existing);
                return [...$existing, 'state' => 'ALREADY_COLLECTED'];
            }
            $acceptance = $this->read("acceptances/{$packageId}.json");
            $fact = ['protocol' => 'PORTER/1', 'kind' => 'COLLECTION', 'collection' => 'CL-' . bin2hex(random_bytes(16)), 'package' => $acceptance['package'], 'acceptance' => $acceptance['acceptance'], 'collector' => $this->sender, 'collected_at_ms' => $this->now(), 'attests' => 'PACKAGE_RECOVERABLY_TRANSFERRED_TO_HOST_CUSTODY'];
            $this->atomic("collections/facts/{$fact['collection']}.json", $fact);
            $this->materializeCollection($fact);
            return [...$fact, 'state' => 'COLLECTED'];
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }

    public function recoverCollections(): void
    {
        $this->folder('collections/facts');
        foreach (glob($this->path('collections/facts/CL-*.json')) ?: [] as $path) {
            $value = json_decode((string)file_get_contents($path), true);
            if (is_array($value)) $this->materializeCollection($value);
        }
    }

    public function abandon(string $ticketId): array
    {
        $this->mutate($ticketId, function (array $ticket) {
            if (!$ticket['abandoned']) {
                $ticket['abandoned'] = true;
                $ticket['events'][] = ['event' => 'ABANDONED', 'at_ms' => $this->now()];
            }
            return $ticket;
        });
        return $this->inspect($ticketId, false);
    }

    private function event(string $ticketId, string $event, array $details = []): void
    {
        $this->mutate($ticketId, function (array $ticket) use ($event, $details) {
            $item = ['event' => $event, 'at_ms' => $this->now()];
            if ($details !== []) $item['details'] = $details;
            $ticket['events'][] = $item;
            return $ticket;
        });
    }
    private function eventAt(array $ticket, string $kind): ?int
    {
        $times = [];
        foreach ($ticket['events'] ?? [] as $event) if (($event['event'] ?? null) === $kind) $times[] = (int)$event['at_ms'];
        return $times === [] ? null : max($times);
    }
    private function materialize(array $lodgement): void
    {
        $ticket = $lodgement['ticket'];
        $package = $lodgement['package'];
        foreach (['lodgements/locks', 'tickets', 'tickets/by-package', 'outgoing', 'receipts', 'refused'] as $folder) $this->folder($folder);
        $lockPath = $this->path("lodgements/locks/{$lodgement['lodgement']}.lock");
        $lock = fopen($lockPath, 'c+');
        if (!$lock || !flock($lock, LOCK_EX)) throw new RuntimeException('Could not recover PORTER lodgement');
        @chmod($lockPath, 0666);
        try {
            if (!is_file($this->path("tickets/{$ticket['ticket']}.json"))) $this->atomic("tickets/{$ticket['ticket']}.json", $ticket);
            $mapping = $this->path("tickets/by-package/{$package['package']}");
            $existing = is_file($mapping) ? trim((string)file_get_contents($mapping)) : null;
            if ($existing !== null && $existing !== $ticket['ticket']) throw new RuntimeException('Package identity is associated with another Collection Ticket');
            if ($existing === null) $this->atomicText("tickets/by-package/{$package['package']}", $ticket['ticket'] . "\n");
            $id = $package['package'];
            $settled = is_file($this->path("receipts/{$id}.json")) || is_file($this->path("refused/{$id}.json"));
            $moving = is_file($this->path("outgoing/{$id}.carrying"));
            if (!$settled && !$moving && !is_file($this->path("outgoing/{$id}.json"))) $this->atomic("outgoing/{$id}.json", $package);
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }
    private function findCollection(string $packageId): ?array
    {
        $mapping = $this->path("collections/by-package/{$packageId}");
        if (is_file($mapping)) return $this->read('collections/facts/' . trim((string)file_get_contents($mapping)) . '.json');
        foreach (glob($this->path('collections/facts/CL-*.json')) ?: [] as $path) {
            $value = json_decode((string)file_get_contents($path), true);
            if (($value['package']['package'] ?? null) === $packageId) return $value;
        }
        return null;
    }
    private function materializeCollection(array $fact): void
    {
        $packageId = $fact['package']['package'];
        if (!is_file($this->path("collected/{$packageId}.json"))) $this->atomic("collected/{$packageId}.json", $fact['package']);
        if (!is_file($this->path("collections/by-package/{$packageId}"))) $this->atomicText("collections/by-package/{$packageId}", $fact['collection'] . "\n");
        @unlink($this->path("inbox/{$packageId}.json"));
    }
    private function readTicket(string $id): array
    {
        return $this->read("tickets/{$id}.json");
    }
    private function read(string $relative): array
    {
        $value = json_decode((string)@file_get_contents($this->path($relative)), true);
        if (!is_array($value)) throw new RuntimeException("Unknown PORTER correspondence {$relative}");
        return $value;
    }
    private function mutate(string $id, callable $change): void
    {
        $lock = fopen($this->path("tickets/{$id}.lock"), 'c+');
        if (!$lock || !flock($lock, LOCK_EX)) throw new RuntimeException('Could not inspect Collection Ticket');
        try {
            $this->atomic("tickets/{$id}.json", $change($this->readTicket($id)));
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }
    private function folder(string $relative): string
    {
        $path = $this->path($relative);
        if (!is_dir($path) && !mkdir($path, 0777, true) && !is_dir($path)) throw new RuntimeException("Could not create PORTER mail slot {$path}");
        return $path;
    }
    private function atomic(string $relative, array $value): void
    {
        $target = $this->path($relative);
        $this->folder(dirname($relative));
        $temporary = dirname($target) . '/.' . basename($target) . '.' . bin2hex(random_bytes(4)) . '.tmp';
        $stream = fopen($temporary, 'wb');
        if (!$stream) throw new RuntimeException('Could not write PORTER durable fact');
        fwrite($stream, json_encode($value, JSON_THROW_ON_ERROR));
        fflush($stream);
        fsync($stream);
        fclose($stream);
        rename($temporary, $target);
    }
    private function atomicText(string $relative, string $value): void
    {
        $target = $this->path($relative);
        $this->folder(dirname($relative));
        $temporary = dirname($target) . '/.' . basename($target) . '.' . bin2hex(random_bytes(4)) . '.tmp';
        $stream = fopen($temporary, 'wb');
        if (!$stream) throw new RuntimeException('Could not write PORTER association');
        fwrite($stream, $value);
        fflush($stream);
        fsync($stream);
        fclose($stream);
        rename($temporary, $target);
    }
    private function path(string $relative): string
    {
        return rtrim($this->ipc, '/') . '/' . $relative;
    }
    private function now(): int
    {
        return (int)round(microtime(true) * 1000);
    }
}
