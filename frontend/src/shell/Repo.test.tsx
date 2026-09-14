/* Every state the Repo view can be in, rendered to markup and read back.
 * No browser: the view is a function of its payload, and the payload's
 * shapes are enumerable -- no repositories, no upstream, ahead, behind,
 * dirty, GitHub absent with a reason, GitHub present with PRs in each check
 * state and issues with labels, both lists empty, and terminals grouped
 * across two repositories with one outside any. */
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Repo, type RepoInfo, type RepoTerminal } from './Panels'

const base: RepoInfo = {
  root: '/Users/me/Developer/x', name: 'x', branch: 'main', upstream: 'origin/main',
  ahead: 0, behind: 0, dirty: [], commits: [], remote: 'git@github.com:me/x.git',
  github: null, github_reason: null, cwds: ['/Users/me/Developer/x'],
}
const one: RepoTerminal[] = [{ id: 't1', mode: 'faber', cwd: '/Users/me/Developer/x', index: 1, showing: true }]
const strip = (html: string) => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')
const text = (repo: Partial<RepoInfo>, terminals: RepoTerminal[] = one) =>
  strip(renderToStaticMarkup(<Repo data={{ repos: [{ ...base, ...repo }], outside: [] }} terminals={terminals} />))

describe('Repo view', () => {
  it('says when a terminal is not in a repository, and how to start one', () => {
    const t = strip(renderToStaticMarkup(
      <Repo data={{ repos: [], outside: ['/Users/me/notes'] }}
            terminals={[{ id: 't1', mode: 'general', cwd: '/Users/me/notes', index: 1, showing: true }]} />))
    expect(t).toContain('Not in a repository')
    expect(t).toContain('general · 1')
    expect(t).toContain('/Users/me/notes')
    expect(t).toContain('git init')
  })

  it('names the terminals in a repository the way the tab strip does', () => {
    const t = text({}, [
      { id: 'a', mode: 'faber', cwd: '/Users/me/Developer/x', index: 1, showing: false },
      { id: 'b', mode: 'faber', cwd: '/Users/me/Developer/x', index: 3, showing: true },
    ])
    expect(t).toContain('Repo · x · main')
    expect(t).toContain('faber · 1')
    expect(t).toContain('faber · 3')
    expect(t).toContain('/Users/me/Developer/x')
  })

  it('groups terminals by repository, the showing one first, the rest under their own headings', () => {
    const y: RepoInfo = { ...base, root: '/Users/me/Developer/y', name: 'y', cwds: ['/Users/me/Developer/y', '/Users/me/Developer/y/backend'] }
    const terminals: RepoTerminal[] = [
      { id: 'a', mode: 'faber', cwd: '/Users/me/Developer/x', index: 1, showing: false },
      { id: 'b', mode: 'faber', cwd: '/Users/me/Developer/y', index: 2, showing: false },
      { id: 'c', mode: 'vesper', cwd: '/Users/me/Developer/y/backend', index: 3, showing: true },
      { id: 'd', mode: 'general', cwd: '/Users/me/notes', index: 4, showing: false },
    ]
    const t = strip(renderToStaticMarkup(
      <Repo data={{ repos: [base, y], outside: ['/Users/me/notes'] }} terminals={terminals} />))
    const yAt = t.indexOf('Repo · y · main'), xAt = t.indexOf('Repo · x · main'), outsideAt = t.indexOf('Not in a repository')
    expect(yAt).toBeGreaterThan(-1); expect(xAt).toBeGreaterThan(-1); expect(outsideAt).toBeGreaterThan(-1)
    expect(yAt).toBeLessThan(xAt)
    expect(xAt).toBeLessThan(outsideAt)
    const yBlock = t.slice(yAt, xAt), xBlock = t.slice(xAt, outsideAt)
    expect(yBlock).toContain('faber · 2'); expect(yBlock).toContain('vesper · 3'); expect(yBlock).not.toContain('faber · 1')
    expect(xBlock).toContain('faber · 1'); expect(xBlock).not.toContain('vesper · 3')
    expect(t.slice(outsideAt)).toContain('general · 4')
  })

  it('folds the commit lists when there is more than one repository, and still says how many', () => {
    const y: RepoInfo = {
      ...base, root: '/Users/me/Developer/y', name: 'y', cwds: ['/Users/me/Developer/y'],
      commits: [
        { sha: 'aaa1111', subject: 'y local', at: Math.floor(Date.now() / 1000) - 60, pushed: false },
        { sha: 'bbb2222', subject: 'y pushed', at: Math.floor(Date.now() / 1000) - 60, pushed: true },
      ],
    }
    const terminals: RepoTerminal[] = [
      { id: 'a', mode: 'faber', cwd: '/Users/me/Developer/x', index: 1, showing: true },
      { id: 'b', mode: 'faber', cwd: '/Users/me/Developer/y', index: 2, showing: false },
    ]
    const t = strip(renderToStaticMarkup(<Repo data={{ repos: [base, y], outside: [] }} terminals={terminals} />))
    expect(t).toContain('Commits · 2 · 1 not on GitHub')
    expect(t).not.toContain('aaa1111'), 'folded: the list is not rendered'
    // Alone, the list is open.
    expect(text({ commits: y.commits })).toContain('aaa1111 y local')
  })

  it('with no upstream, says how to publish the branch', () => {
    const t = text({ upstream: null, ahead: null, behind: null, branch: 'job/12-thing' })
    expect(t).toContain('no upstream')
    expect(t).toContain('git push -u origin job/12-thing')
  })

  it('counts what is not on GitHub, what is behind, and what is uncommitted -- and says what to do', () => {
    const t = text({
      ahead: 201, behind: 2, dirty: ['a.ts', 'b.ts'],
      commits: [
        { sha: 'abc1234', subject: 'newest, local only', at: Math.floor(Date.now() / 1000) - 90, pushed: false },
        { sha: 'def5678', subject: 'older, on GitHub', at: Math.floor(Date.now() / 1000) - 7200, pushed: true },
      ],
    })
    expect(t).toContain('↑ 201 not on GitHub')
    expect(t).toContain('↓ 2 behind')
    expect(t).toContain('2 uncommitted')
    expect(t).toContain('201 commits on this machine only')
    expect(t).toContain('a session never pushes')
    expect(t).toContain('2 commits on GitHub that this machine does not have')
    expect(t).toContain('2 files changed and not committed')
    expect(t).toContain('a.ts'); expect(t).toContain('b.ts')
    expect(t).toContain('● abc1234 newest, local only 1m')
    expect(t).toContain('· def5678 older, on GitHub 2h')
  })

  it('says everything is on GitHub when it is', () => {
    expect(text({})).toContain('Everything here is on GitHub and nothing is uncommitted')
  })

  it('keeps the local half when GitHub is not available, and says why', () => {
    const t = text({ github_reason: 'gh could not reach GitHub (not signed in, offline, or gh is not installed)' })
    expect(t).toContain('Not available: gh could not reach GitHub')
    expect(t).toContain('Commits')
  })

  it('shows pull requests in every check state, drafts, conflicts, and issues with labels', () => {
    const t = text({
      github: {
        slug: 'me/x', url: 'https://github.com/me/x', private: false, default_branch: 'main',
        pull_requests: [
          { number: 7, title: 'Green one', branch: 'job/7-green', draft: false, mergeable: 'MERGEABLE', url: 'u', checks: 'pass' },
          { number: 8, title: 'Red one', branch: 'job/8-red', draft: true, mergeable: 'CONFLICTING', url: 'u', checks: 'fail' },
          { number: 9, title: 'Waiting', branch: 'job/9', draft: false, mergeable: 'UNKNOWN', url: 'u', checks: 'pending' },
          { number: 10, title: 'No CI', branch: 'job/10', draft: false, mergeable: 'MERGEABLE', url: 'u', checks: null },
        ],
        issues: [{ number: 12, title: 'Do the thing', url: 'u', labels: ['bug', 'faber'] }],
      },
    })
    expect(t).toContain('me/x · public ↗')
    expect(t).toContain('pull requests · 4 open')
    expect(t).toContain('#7 Green one job/7-green checks pass')
    expect(t).toContain('#8 Red one job/8-red draft checks fail conflicts')
    expect(t).toContain('#9 Waiting job/9 checks pending')
    expect(t).toContain('#10 No CI job/10')
    expect(t).not.toContain('#10 No CI job/10 checks')
    expect(t).toContain('issues · 1 open')
    expect(t).toContain('#12 Do the thing bug faber')
  })

  it('explains what an empty PR list and an empty issue list are for', () => {
    const t = text({ github: { slug: 'me/x', url: null, private: true, default_branch: 'main', pull_requests: [], issues: [] } })
    expect(t).toContain('me/x · private')
    expect(t).toContain('a branch pushed with a PR is how work gets reviewed before it reaches main')
    expect(t).toContain('an issue per piece of work is the backlog')
  })
})
