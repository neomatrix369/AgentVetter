import path from 'node:path';

/** Config home dir name under $HOME (ADR-0018). */
export const CONFIG_HOME_NAME = '.agentvetter';

const HOOK_SUFFIXES = [
  '/.agentvetter/hooks/pre-tool-use.sh',
];

/**
 * Resolve AgentVetter config home under `homedir`.
 * Always `~/.agentvetter` (no legacy fallback).
 */
export function resolveConfigHome(homedir) {
  return path.join(homedir, CONFIG_HOME_NAME);
}

/** True when a Claude settings hook command points at our PreToolUse handler. */
export function isAgentVetterHookCommand(command, homedir) {
  if (typeof command !== 'string') return false;
  const expanded = command.startsWith('~/')
    ? path.join(homedir, command.slice(2))
    : command;
  return HOOK_SUFFIXES.some((suffix) => expanded.endsWith(suffix));
}

/** Env: `AGENTVETTER_<name>` only. */
export function envPrefer(name, { env = process.env } = {}) {
  return env[`AGENTVETTER_${name}`];
}
