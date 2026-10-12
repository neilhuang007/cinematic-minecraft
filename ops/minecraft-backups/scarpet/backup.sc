// Installed as backup.sc and checkpoint.sc. Both use the same Borg worker.
__config() -> {
    'scope' -> 'global',
    'stay_loaded' -> true,
    'command_permission' -> 'ops'
};

// player() may select a nearby player for console calls; use the actual source.
_requester() -> (
    caller = system_info('source_entity');
    if(caller, query(caller, 'name'), 'Server')
);

__command() -> (
    logger('info', '[MC_BACKUP_REQUEST] '+_requester());
    'Checkpoint requested. You will receive a completion message.'
);

status() -> (
    logger('info', '[MC_BACKUP_STATUS] '+_requester());
    'Checking backup status...'
);
