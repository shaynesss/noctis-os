/* The slash-command list.
 *
 * Named slash.ts, not commands.ts: a lowercase sibling of a component file
 * collides on a case-insensitive filesystem and the wrong module wins the
 * import. Third time this session — md.ts, grid.ts, and now this.
 *
 * Data and a matcher, kept out of the component file so it can be imported
 * without dragging React in — and so fast refresh keeps working, which it
 * does not for a module exporting both components and constants.
 *
 * Every command maps to something the shell can already do. That is the
 * rule: a menu of commands is a promise, and listing one that is not
 * implemented is the same lie as a shortcut that does nothing.
 */
export interface Command {
  name: string
  summary: string
}

export const COMMANDS: Command[] = [
  { name: 'model', summary: 'Change the model for this session' },
  { name: 'permissions', summary: 'Set what this session may do without asking' },
  { name: 'handoff', summary: 'Hand this conversation to another mode' },
  { name: 'search', summary: 'Search conversations and the vault' },
  { name: 'clear', summary: 'Start a fresh conversation in this tab' },
]

export const matching = (typed: string): Command[] => {
  const term = typed.replace(/^\//, '').toLowerCase()
  return COMMANDS.filter((c) => c.name.startsWith(term))
}
