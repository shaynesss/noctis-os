// Faber's Lodge tab -- vault-native design-asset catalog + quick-capture
// inbox. New tab inside the Faber card (ProfileOverlay.tsx), not a
// standalone screen, per noctis-os/SPEC.md's Design Brief amendment
// (2026-07-24). Card chrome (paper background, --accent border language)
// is inherited from the parent overlay; this component only owns its own
// content region.
import { useEffect, useState } from 'react'
import {
  LODGE_CATEGORIES,
  addLodgeInboxItem,
  createLodgeEntry,
  getLodgeEntries,
  getLodgeEntry,
  getLodgeInbox,
  getLodgePreviewUrl,
  processLodgeInboxItem,
  updateLodgeEntry,
  uploadLodgePreview,
  type LodgeEntry,
  type LodgeEntryDetail,
  type LodgeInboxItem,
} from './api'

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve((reader.result as string).split(',')[1] ?? '')
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// Browse view is preview-first (locked Design Brief decision) -- fetched as
// an authenticated blob (see api.ts's getLodgePreviewUrl), never a
// token-in-URL <img src>. One instance per entry that actually has a
// preview; entries without one render no thumbnail slot at all.
function LodgeThumb({ slug, size }: { slug: string; size: 'small' | 'large' }) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    getLodgePreviewUrl(slug).then((fetched) => {
      if (cancelled) {
        if (fetched) URL.revokeObjectURL(fetched)
        return
      }
      objectUrl = fetched
      setUrl(fetched)
    })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [slug])

  if (!url) return null
  return <img src={url} alt="" className={`lodge-thumb lodge-thumb-${size}`} />
}

interface EntryFormValues {
  slug: string
  name: string
  category: string
  tags: string
  source: string
  code: string
  reference: string
}

const BLANK_FORM: EntryFormValues = {
  slug: '',
  name: '',
  category: LODGE_CATEGORIES[0],
  tags: '',
  source: '',
  code: '',
  reference: '',
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export default function DesignLodgeTab() {
  const [entries, setEntries] = useState<LodgeEntry[] | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const [expandedSlug, setExpandedSlug] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, LodgeEntryDetail>>({})
  const [addOpen, setAddOpen] = useState(false)
  const [editSlug, setEditSlug] = useState<string | null>(null)
  const [form, setForm] = useState<EntryFormValues>(BLANK_FORM)
  const [formImage, setFormImage] = useState<File | null>(null)
  const [inbox, setInbox] = useState<LodgeInboxItem[] | null>(null)
  const [captureLink, setCaptureLink] = useState('')
  const [captureNote, setCaptureNote] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    refreshEntries()
    refreshInbox()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category])

  function refreshEntries() {
    getLodgeEntries(category ?? undefined).then(setEntries)
  }

  function refreshInbox() {
    getLodgeInbox().then(setInbox)
  }

  function flash(text: string) {
    setNotice(text)
    setTimeout(() => setNotice((current) => (current === text ? null : current)), 2200)
  }

  async function toggleExpand(slug: string) {
    if (expandedSlug === slug) {
      setExpandedSlug(null)
      return
    }
    setExpandedSlug(slug)
    if (!detail[slug]) {
      const full = await getLodgeEntry(slug)
      setDetail((prev) => ({ ...prev, [slug]: full }))
    }
  }

  function openEdit(entry: LodgeEntryDetail) {
    const body = entry.body ?? ''
    const codeMatch = /## Code\n\n```\n([\s\S]*?)\n```/.exec(body)
    const referenceMatch = /## Reference\n\n([\s\S]*)$/.exec(body)
    setForm({
      slug: entry.slug,
      name: entry.name,
      category: entry.category,
      tags: entry.tags.join(', '),
      source: entry.source,
      code: codeMatch?.[1] ?? '',
      reference: referenceMatch?.[1]?.trim() ?? '',
    })
    setEditSlug(entry.slug)
    setAddOpen(false)
    setFormImage(null)
  }

  function openAdd() {
    setForm(BLANK_FORM)
    setEditSlug(null)
    setFormImage(null)
    setAddOpen(true)
  }

  function closeForm() {
    setAddOpen(false)
    setEditSlug(null)
    setFormImage(null)
  }

  async function submitForm() {
    const tags = form.tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    let slug: string
    if (editSlug) {
      slug = editSlug
      await updateLodgeEntry(editSlug, {
        name: form.name,
        category: form.category,
        tags,
        source: form.source,
        code: form.code,
        reference: form.reference,
      })
      flash('saved')
    } else {
      slug = form.slug.trim() || slugify(form.name)
      if (!slug) return
      await createLodgeEntry({
        slug,
        name: form.name,
        category: form.category,
        tags,
        source: form.source,
        code: form.code,
        reference: form.reference,
      })
      flash('added to the Lodge')
    }
    if (formImage) {
      await uploadLodgePreview(slug, await fileToBase64(formImage))
    }
    closeForm()
    refreshEntries()
    setDetail({})
  }

  async function submitCapture() {
    if (!captureLink.trim()) return
    await addLodgeInboxItem(captureLink.trim(), captureNote.trim())
    setCaptureLink('')
    setCaptureNote('')
    flash('captured -- sorted next session')
    refreshInbox()
  }

  async function dismissInboxItem(slug: string) {
    await processLodgeInboxItem(slug)
    refreshInbox()
  }

  const canSubmitForm = form.name.trim().length > 0 && (editSlug !== null || form.slug.trim().length > 0 || form.name.trim().length > 0)

  return (
    <div className="lodge">
      <div className="lodge-categories">
        {LODGE_CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            className={`lodge-chip${category === cat ? ' active' : ''}`}
            onClick={() => setCategory((current) => (current === cat ? null : cat))}
          >
            {cat.toLowerCase()}
          </button>
        ))}
      </div>

      <div className="lodge-list-header">
        <span className="lodge-count">{entries ? `${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}` : 'loading…'}</span>
        <button type="button" className="lodge-add-btn" onClick={openAdd}>
          + add
        </button>
      </div>

      <div className="lodge-list">
        {entries && entries.length === 0 && (
          <p className="idle-note lodge-empty">nothing here yet -- check first, but don't stall.</p>
        )}
        {entries?.map((entry) => {
          const isOpen = expandedSlug === entry.slug
          const full = detail[entry.slug]
          return (
            <div key={entry.slug} className={`lodge-entry${entry.superseded_by ? ' superseded' : ''}`}>
              <button type="button" className="lodge-entry-summary" onClick={() => toggleExpand(entry.slug)}>
                <span className={`job-caret${isOpen ? ' open' : ''}`}>▸</span>
                {entry.has_preview && <LodgeThumb slug={entry.slug} size="small" />}
                <span className="lodge-entry-name">{entry.name}</span>
                <span className="lodge-entry-category">{entry.category}</span>
              </button>
              {isOpen && (
                <div className="lodge-entry-detail">
                  {entry.has_preview && <LodgeThumb slug={entry.slug} size="large" />}
                  {entry.tags.length > 0 && (
                    <div className="lodge-tags">
                      {entry.tags.map((tag) => (
                        <span key={tag} className="lodge-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {entry.source && <p className="lodge-source">{entry.source}</p>}
                  {entry.superseded_by && (
                    <p className="lodge-superseded-note">superseded by {entry.superseded_by}</p>
                  )}
                  {full ? (
                    <pre className="lodge-body">{full.body.replace(/^---[\s\S]*?---\n\n/, '')}</pre>
                  ) : (
                    <p className="lodge-loading">loading…</p>
                  )}
                  <button
                    type="button"
                    className="lodge-edit-btn"
                    onClick={() => full && openEdit(full)}
                    disabled={!full}
                  >
                    edit
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {(addOpen || editSlug) && (
        <div className="lodge-form">
          <h4>{editSlug ? 'EDIT ENTRY' : 'NEW ENTRY'}</h4>
          <label>
            <span>name</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus />
          </label>
          {!editSlug && (
            <label>
              <span>slug</span>
              <input
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                placeholder={slugify(form.name) || 'auto from name'}
              />
            </label>
          )}
          <label>
            <span>category</span>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {LODGE_CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>tags</span>
            <input
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="comma, separated"
            />
          </label>
          <label>
            <span>source</span>
            <input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
          </label>
          <label>
            <span>code</span>
            <textarea
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              rows={3}
            />
          </label>
          <label>
            <span>reference</span>
            <textarea
              value={form.reference}
              onChange={(e) => setForm({ ...form, reference: e.target.value })}
              rows={2}
            />
          </label>
          <label>
            <span>visual{formImage ? ` — ${formImage.name}` : ''}</span>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setFormImage(e.target.files?.[0] ?? null)}
            />
          </label>
          <div className="lodge-form-actions">
            <button type="button" className="new-build-cancel" onClick={closeForm}>
              cancel
            </button>
            <button type="button" className="new-build-submit" disabled={!canSubmitForm} onClick={submitForm}>
              {editSlug ? 'save' : 'add to lodge'}
            </button>
          </div>
        </div>
      )}

      <div className="lodge-capture">
        <span className="lodge-capture-label">quick capture</span>
        <input
          value={captureLink}
          onChange={(e) => setCaptureLink(e.target.value)}
          placeholder="paste a link"
          className="lodge-capture-link"
        />
        <input
          value={captureNote}
          onChange={(e) => setCaptureNote(e.target.value)}
          placeholder="short note"
          className="lodge-capture-note"
        />
        <button type="button" className="lodge-capture-btn" disabled={!captureLink.trim()} onClick={submitCapture}>
          capture
        </button>
        {inbox && inbox.length > 0 && (
          <div className="lodge-inbox-list">
            {inbox.map((item) => (
              <div key={item.slug} className="lodge-inbox-row">
                <span className="lodge-inbox-note">{item.note || item.link}</span>
                <button type="button" className="lodge-inbox-dismiss" onClick={() => dismissInboxItem(item.slug)}>
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {notice && <p className="lodge-notice">{notice}</p>}
    </div>
  )
}
