/* Every state the Repo view can be in, rendered to markup and read back.
 * No browser: the view is a function of its payload, and the payload's
 * shapes are enumerable -- no repositories, no upstream, ahead, behind,
 * dirty, terminals grouped across two repositories with one outside any,
 * and the GitHub card in each of its states: pending, absent with a
 * reason, present with PRs in each check state and issues with labels,
 * both lists empty. */
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { GithubCard, Repo, type GithubInfo, type RepoInfo, type RepoTerminal } from './Panels'

const base: RepoInfo = {
  root: '/Users/me/Developer/x', name: 'x', branch: 'main', upstream: 'origin/main',
  ahead: 0, behind: 0, dirty: [], commits: [], remote: 'git@github.com:me/x.git',
  slug: 'me/x', github_reason: null, cwds: ['/Users/me/Developer/x'],
}
const one: RepoTerminal[] = [{ id: 't1', mode: 'faber', cwd: '/Users/me/Developer/x', index: 1, showing: true }]
const strip = (html: string) => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')
const text = (repo: Partial<RepoInfo>, terminals: RepoTerminal[] = one) =>
  strip(renderToStaticMarkup(<Repo data={{ repos: [{ ...base, ...repo }], outside: [] }} terminals={terminals} />))
const github = (gh: GithubInfo | null, reason: string | null = null, pending = false) =>
  strip(renderToStaticMarkup(<GithubCard gh={gh} reason={reason} pending={pending} />))

describe('Repo view', () => {
  it('gives a terminal outside any repository no module and no section', () => {
    // A "not in a repository" section told the reader nothing they could act
    // on here, and every mode starts in a repository now (2026-09-16).
    const t = strip(renderToStaticMarkup(
      <Repo data={{ repos: [], outside: ['/Users/me/notes'] }}
            terminals={[{ id: 't1', mode: 'general', cwd: '/Users/me/notes', index: 1, showing: true }]} />))
    expect(t).not.toContain('Not in a repository')
    expect(t).not.toContain('/Users/me/notes')
    expect(t.trim()).toBe('')
  })

  it('names the terminals in a repository the way the tab strip does, and links the slug', () => {
    const t = text({}, [
      { id: 'a', mode: 'faber', cwd: '/Users/me/Developer/x', index: 1, showing: false },
      { id: 'b', mode: 'faber', cwd: '/Users/me/Developer/x', index: 3, showing: true },
    ])
    expect(t).toContain('x · main')
    expect(t).toContain('faber · 1')
    expect(t).toContain('faber · 3')
    expect(t).toContain('/Users/me/Developer/x')
    expect(t).toContain('me/x ↗')
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
    const yAt = t.indexOf('y · main'), xAt = t.indexOf('x · main')
    expect(yAt).toBeGreaterThan(-1); expect(xAt).toBeGreaterThan(-1)
    expect(yAt).toBeLessThan(xAt)
    const yBlock = t.slice(yAt, xAt), xBlock = t.slice(xAt)
    expect(yBlock).toContain('faber · 2'); expect(yBlock).toContain('vesper · 3'); expect(yBlock).not.toContain('faber · 1')
    expect(xBlock).toContain('faber · 1'); expect(xBlock).not.toContain('vesper · 3')
    // The terminal outside any repository appears nowhere (2026-09-16).
    expect(t).not.toContain('general · 4'); expect(t).not.toContain('Not in a repository')
  })

  it('folds every commit list, whatever is on screen, and still says how many', () => {
    const y: RepoInfo = {
      ...base, root: '/Users/me/Developer/y', name: 'y', cwds: ['/Users/me/Developer/y'],
      commits: [
        { sha: 'aaa1111', full: 'aaa1111aaa11', subject: 'y local', body: '', at: Math.floor(Date.now() / 1000) - 60, pushed: false },
        { sha: 'bbb2222', full: 'bbb2222bbb22', subject: 'y pushed', body: '', at: Math.floor(Date.now() / 1000) - 60, pushed: true },
      ],
    }
    const terminals: RepoTerminal[] = [
      { id: 'a', mode: 'faber', cwd: '/Users/me/Developer/x', index: 1, showing: true },
      { id: 'b', mode: 'faber', cwd: '/Users/me/Developer/y', index: 2, showing: false },
    ]
    const t = strip(renderToStaticMarkup(<Repo data={{ repos: [base, y], outside: [] }} terminals={terminals} />))
    expect(t).toContain('Commits · 1 of 2 not on GitHub')
    expect(t).not.toContain('bbb2222'), 'folded: the list itself is not rendered'
    // And alone too (2026-09-17): a lone repository used to open its twenty
    // rows on arrival, which is a screen of history nobody asked for and it
    // pushed the record and GitHub off the bottom of the module.
    const alone = text({ commits: y.commits })
    expect(alone).toContain('Commits · 1 of 2 not on GitHub')
    expect(alone).not.toContain('aaa1111 y local')
  })

  it('with no upstream, offers to publish the branch', () => {
    const t = text({ upstream: null, ahead: null, behind: null, branch: 'job/12-thing' })
    expect(t).toContain('no upstream')
    expect(t).toContain('publish job/12-thing')
  })

  it('offers a force push only when the histories disagree, and a plain one otherwise', () => {
    const diverged = text({ ahead: 281, behind: 280 })
    expect(diverged).toContain('↑ 281 not on GitHub'); expect(diverged).toContain('↓ 280 behind')
    expect(diverged).toContain('push · force')
    const plain = text({ ahead: 3, behind: 0 })
    expect(plain).toContain('push 3')
    expect(plain).not.toContain('force')
    expect(text({})).not.toContain('push ')
  })

  it('counts what is not on GitHub, what is behind, and what is uncommitted -- figures and files, no sentence', () => {
    const t = text({
      ahead: 201, behind: 2, dirty: ['a.ts', 'b.ts'],
      commits: [
        { sha: 'abc1234', full: 'abc1234abc12', subject: 'newest, local only', body: '', at: Math.floor(Date.now() / 1000) - 90, pushed: false },
        { sha: 'def5678', full: 'def5678def56', subject: 'older, on GitHub', body: '', at: Math.floor(Date.now() / 1000) - 7200, pushed: true },
      ],
    })
    expect(t).toContain('↑ 201 not on GitHub')
    expect(t).toContain('↓ 2 behind')
    expect(t).toContain('2 uncommitted')
    // No sentence between the figures and the files (2026-09-16): the count
    // and the list are the fact, and the push button sits on the Commits
    // fold, the thing it pushes. A module with nothing uncommitted lists
    // nothing.
    expect(t).not.toContain('files changed and not committed'); expect(t).not.toContain('Push puts')
    expect(text({ ahead: 5 })).toContain('push 5')
    expect(t).toContain('a.ts'); expect(t).toContain('b.ts'); expect(t).not.toContain('Uncommitted ·')
    expect(text({ dirty: [] })).not.toContain('a.ts')
    // The figures are above the fold; the rows are behind it.
    expect(t).toContain('Commits · 1 of 2 not on GitHub')
    expect(t).not.toContain('abc1234 newest, local only')
  })

  it('says nothing at all when everything is on GitHub and committed', () => {
    const t = text({})
    expect(t).toContain('↑ 0 not on GitHub'); expect(t).toContain('0 uncommitted')
    expect(t).not.toContain('Everything here'); expect(t).not.toContain('push ')
  })

  it('says why there is no GitHub half when the remote is not there', () => {
    const t = text({ slug: null, github_reason: 'no remote named origin' })
    expect(t).toContain('not available: no remote named origin')
    expect(t).toContain('Commits')
  })
})

describe('GitHub card', () => {
  it('says it is asking, then says why it could not', () => {
    expect(github(null, null, true)).toContain('Asking GitHub…')
    expect(github(null, 'gh could not reach GitHub (not signed in, offline, or gh is not installed)'))
      .toContain('Not available: gh could not reach GitHub')
  })

  it('shows pull requests in every check state, drafts, conflicts, and issues with labels', () => {
    const t = github({
      slug: 'me/x', url: 'https://github.com/me/x', private: false, default_branch: 'main',
      pull_requests: [
        { number: 7, title: 'Green one', branch: 'job/7-green', draft: false, mergeable: 'MERGEABLE', url: 'u', checks: 'pass' },
        { number: 8, title: 'Red one', branch: 'job/8-red', draft: true, mergeable: 'CONFLICTING', url: 'u', checks: 'fail' },
        { number: 9, title: 'Waiting', branch: 'job/9', draft: false, mergeable: 'UNKNOWN', url: 'u', checks: 'pending' },
        { number: 10, title: 'No CI', branch: 'job/10', draft: false, mergeable: 'MERGEABLE', url: 'u', checks: null },
      ],
      issues: [{ number: 12, title: 'Do the thing', url: 'u', labels: ['bug', 'faber'] }],
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
    const t = github({ slug: 'me/x', url: null, private: true, default_branch: 'main', pull_requests: [], issues: [] })
    expect(t).toContain('me/x · private')
    expect(t).toContain('a branch pushed with a PR is how work gets reviewed before it reaches main')
    expect(t).toContain('an issue per piece of work is the backlog')
  })
})
