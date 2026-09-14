/* Every state the Repo view can be in, rendered to markup and read back.
 * No browser: the view is a function of its payload, and the payload's
 * shapes are enumerable -- not a repo, no upstream, ahead, behind, dirty,
 * GitHub absent with a reason, GitHub present with PRs in each check state
 * and issues with labels, and both lists empty. */
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Repo, type RepoPayload } from './Panels'

const base: NonNullable<RepoPayload['repo']> = {
  root: '/Users/me/Developer/x', name: 'x', branch: 'main', upstream: 'origin/main',
  ahead: 0, behind: 0, dirty: [], commits: [], remote: 'git@github.com:me/x.git',
  github: null, github_reason: null,
}
const text = (repo: RepoPayload['repo'], cwd = '/Users/me/Developer/x') =>
  renderToStaticMarkup(<Repo data={{ repo }} cwd={cwd} />).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')

describe('Repo view', () => {
  it('says when the directory is not a repository, and how to start one', () => {
    const t = text(null, '/Users/me/notes')
    expect(t).toContain('/Users/me/notes')
    expect(t).toContain('not inside a git repository')
    expect(t).toContain('git init')
  })

  it('with no upstream, says how to publish the branch', () => {
    const t = text({ ...base, upstream: null, ahead: null, behind: null, branch: 'job/12-thing' })
    expect(t).toContain('no upstream')
    expect(t).toContain('git push -u origin job/12-thing')
  })

  it('counts what is not on GitHub, what is behind, and what is uncommitted -- and says what to do', () => {
    const t = text({
      ...base, ahead: 201, behind: 2, dirty: ['a.ts', 'b.ts'],
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
    expect(text(base)).toContain('Everything here is on GitHub and nothing is uncommitted')
  })

  it('keeps the local half when GitHub is not available, and says why', () => {
    const t = text({ ...base, github_reason: 'gh could not reach GitHub (not signed in, offline, or gh is not installed)' })
    expect(t).toContain('Not available: gh could not reach GitHub')
    expect(t).toContain('Commits')
  })

  it('shows pull requests in every check state, drafts, conflicts, and issues with labels', () => {
    const t = text({
      ...base,
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
    const t = text({ ...base, github: { slug: 'me/x', url: null, private: true, default_branch: 'main', pull_requests: [], issues: [] } })
    expect(t).toContain('me/x · private')
    expect(t).toContain('a branch pushed with a PR is how work gets reviewed before it reaches main')
    expect(t).toContain('an issue per piece of work is the backlog')
  })
})
