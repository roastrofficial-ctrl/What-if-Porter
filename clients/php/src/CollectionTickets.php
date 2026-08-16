<?php

namespace Porter\Client;

use RuntimeException;

final class CollectionTickets
{
    public function __construct(private readonly string $ipc, private readonly string $sender) {}

    public function deposit(string $recipient, string $kind, array $payload, int $ttl = 300): array
    {
        $now = time();
        $packageId = 'PKG-' . bin2hex(random_bytes(16));
        $ticketId = 'CT-' . bin2hex(random_bytes(16));
        $package = ['protocol' => 'PORTER/1', 'package' => $packageId, 'from' => $this->sender, 'to' => $recipient, 'kind' => $kind, 'created' => $now, 'expires' => $now + $ttl, 'reply_to' => $this->sender, 'payload' => $payload];
        $ticket = ['protocol' => 'PORTER/1', 'ticket' => $ticketId, 'package' => $packageId, 'created' => $now, 'expires' => $now + $ttl, 'abandoned' => false, 'collected_return' => null, 'events' => [['event' => 'DEPOSITED', 'at_ms' => $this->now()]]];
        foreach (['tickets', 'tickets/by-package', 'outgoing', 'inbox', 'collected'] as $folder) $this->folder($folder);
        $this->atomic("tickets/{$ticketId}.json", $ticket);
        file_put_contents($this->path("tickets/by-package/{$packageId}"), $ticketId . "\n");
        $this->atomic("outgoing/{$packageId}.json", $package);
        return $ticket;
    }

    public function inspect(string $ticketId, bool $record = true): array
    {
        $ticket = $this->readTicket($ticketId);
        $returns = [];
        foreach (glob($this->path('inbox/PKG-*.json')) ?: [] as $path) {
            $value = json_decode((string)file_get_contents($path), true);
            if (($value['in_reply_to'] ?? null) === $ticket['package']) $returns[] = $value['package'];
        }
        if ($ticket['collected_return']) $state = 'COLLECTED';
        elseif ($ticket['abandoned'] && $returns) $state = 'ABANDONED_WITH_RETURN';
        elseif ($ticket['abandoned']) $state = 'ABANDONED';
        elseif ($returns) $state = 'RETURN_HELD';
        elseif ($ticket['expires'] <= time()) $state = 'EXPIRED_OBSERVED';
        else $state = 'OUTSTANDING';
        if ($record) $this->event($ticketId, 'TICKET_INSPECTED', ['observed_state' => $state, 'held_returns' => count($returns)]);
        return [...$ticket, 'state' => $state, 'held_returns' => $returns, 'duplicate_returns' => max(0, count($returns) - 1)];
    }

    public function collect(string $ticketId): array
    {
        $status = $this->inspect($ticketId, false);
        if ($status['collected_return']) return ['state' => 'ALREADY_COLLECTED', 'return' => $status['collected_return'], 'package' => $this->read("collected/{$status['collected_return']}.json")];
        if ($status['held_returns'] === []) return ['state' => $status['state'], 'package' => null];
        sort($status['held_returns']);
        $returnId = $status['held_returns'][0];
        if (!@rename($this->path("inbox/{$returnId}.json"), $this->path("collected/{$returnId}.json"))) return ['state' => 'COLLECTION_CONTESTED', 'package' => null];
        $this->mutate($ticketId, function (array $ticket) use ($returnId) {
            $ticket['collected_return'] = $returnId;
            $ticket['events'][] = ['event' => 'RETURN_COLLECTED', 'at_ms' => $this->now(), 'details' => ['return' => $returnId]];
            return $ticket;
        });
        return ['state' => 'COLLECTED', 'return' => $returnId, 'package' => $this->read("collected/{$returnId}.json"), 'duplicates_retained' => max(0, count($status['held_returns']) - 1)];
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
        $temporary = dirname($target) . '/.' . basename($target) . '.' . bin2hex(random_bytes(4)) . '.tmp';
        file_put_contents($temporary, json_encode($value, JSON_THROW_ON_ERROR));
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
