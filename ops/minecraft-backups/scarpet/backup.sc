// Installed as backup.sc and checkpoint.sc. Both use the same Borg worker.
__config() -> {
    'scope' -> 'global',
    'stay_loaded' -> true,
    'command_permission' -> 'ops'
};

_requester() -> if(player(), query(player(), 'name'), 'Server');

__command() -> (
    logger('info', '[MC_BACKUP_REQUEST] '+_requester());
    'Checkpoint requested. You will receive a completion message.'
);

status() -> (
    logger('info', '[MC_BACKUP_STATUS] '+_requester());
    'Checking backup status...'
);
