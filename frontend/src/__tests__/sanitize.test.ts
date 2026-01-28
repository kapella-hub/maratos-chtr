import { describe, it, expect } from 'vitest'
import {
  sanitizeHtml,
  sanitizeSvg,
  containsDangerousHtml,
  ALLOWED_TAGS,
  FORBIDDEN_ATTRS,
} from '../lib/sanitize'

describe('HTML Sanitization', () => {
  describe('sanitizeHtml', () => {
    it('allows safe HTML tags', () => {
      const input = '<p>Hello <strong>world</strong>!</p>'
      const result = sanitizeHtml(input)
      expect(result).toBe('<p>Hello <strong>world</strong>!</p>')
    })

    it('allows lists', () => {
      const input = '<ul><li>Item 1</li><li>Item 2</li></ul>'
      const result = sanitizeHtml(input)
      expect(result).toContain('<ul>')
      expect(result).toContain('<li>')
    })

    it('allows tables', () => {
      const input = '<table><thead><tr><th>Header</th></tr></thead><tbody><tr><td>Cell</td></tr></tbody></table>'
      const result = sanitizeHtml(input)
      expect(result).toContain('<table>')
      expect(result).toContain('<th>')
      expect(result).toContain('<td>')
    })

    it('allows code blocks', () => {
      const input = '<pre><code>const x = 1;</code></pre>'
      const result = sanitizeHtml(input)
      expect(result).toContain('<pre>')
      expect(result).toContain('<code>')
    })

    it('allows links with href', () => {
      const input = '<a href="https://example.com">Link</a>'
      const result = sanitizeHtml(input)
      expect(result).toContain('href="https://example.com"')
    })

    it('strips script tags completely', () => {
      const input = '<p>Safe</p><script>alert("xss")</script><p>Also safe</p>'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('<script>')
      expect(result).not.toContain('alert')
      expect(result).toContain('Safe')
      expect(result).toContain('Also safe')
    })

    it('strips inline script handlers', () => {
      const input = '<button onclick="alert(1)">Click</button>'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('onclick')
      expect(result).not.toContain('alert')
    })

    it('strips all on* event handlers', () => {
      const handlers = [
        'onclick', 'onload', 'onerror', 'onmouseover', 'onfocus',
        'onblur', 'onkeydown', 'onsubmit', 'onchange',
      ]

      for (const handler of handlers) {
        const input = `<div ${handler}="alert(1)">Content</div>`
        const result = sanitizeHtml(input)
        expect(result).not.toContain(handler)
        expect(result).not.toContain('alert')
      }
    })

    it('strips iframe tags', () => {
      const input = '<iframe src="https://evil.com"></iframe>'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('<iframe')
      expect(result).not.toContain('evil.com')
    })

    it('strips style tags', () => {
      const input = '<style>body { display: none; }</style><p>Content</p>'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('<style>')
      expect(result).not.toContain('display: none')
      expect(result).toContain('Content')
    })

    it('strips object and embed tags', () => {
      const input = '<object data="malware.swf"></object><embed src="malware.swf">'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('<object')
      expect(result).not.toContain('<embed')
    })

    it('strips javascript: URLs', () => {
      const input = '<a href="javascript:alert(1)">Click</a>'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('javascript:')
    })

    it('strips data: URLs (except safe images)', () => {
      const input = '<a href="data:text/html,<script>alert(1)</script>">Click</a>'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('data:text/html')
    })

    it('preserves safe class attributes', () => {
      const input = '<div class="highlight">Content</div>'
      const result = sanitizeHtml(input)
      expect(result).toContain('class="highlight"')
    })

    it('handles nested malicious content', () => {
      const input = '<div><p><span onclick="alert(1)"><script>x</script>Safe text</span></p></div>'
      const result = sanitizeHtml(input)
      expect(result).not.toContain('onclick')
      expect(result).not.toContain('<script>')
      expect(result).toContain('Safe text')
    })
  })

  describe('sanitizeSvg', () => {
    it('allows basic SVG elements', () => {
      const input = '<svg viewBox="0 0 100 100"><rect x="10" y="10" width="80" height="80"/></svg>'
      const result = sanitizeSvg(input)
      expect(result).toContain('<svg')
      expect(result).toContain('<rect')
    })

    it('allows path elements', () => {
      const input = '<svg><path d="M10 10 L90 90"/></svg>'
      const result = sanitizeSvg(input)
      expect(result).toContain('<path')
      expect(result).toContain('d="M10 10 L90 90"')
    })

    it('allows text elements', () => {
      const input = '<svg><text x="50" y="50">Hello</text></svg>'
      const result = sanitizeSvg(input)
      expect(result).toContain('<text')
      expect(result).toContain('Hello')
    })

    it('allows gradients', () => {
      const input = '<svg><defs><linearGradient id="grad"><stop offset="0%" stop-color="red"/></linearGradient></defs></svg>'
      const result = sanitizeSvg(input)
      expect(result).toContain('<linearGradient')
      expect(result).toContain('<stop')
    })

    it('strips script elements in SVG', () => {
      const input = '<svg><script>alert(1)</script><rect/></svg>'
      const result = sanitizeSvg(input)
      expect(result).not.toContain('<script>')
      expect(result).not.toContain('alert')
    })

    it('strips foreignObject (can contain HTML)', () => {
      const input = '<svg><foreignObject><div onclick="alert(1)">HTML</div></foreignObject></svg>'
      const result = sanitizeSvg(input)
      expect(result).not.toContain('<foreignObject')
      expect(result).not.toContain('onclick')
    })

    it('strips SVG event handlers', () => {
      const input = '<svg onload="alert(1)"><rect onclick="alert(2)"/></svg>'
      const result = sanitizeSvg(input)
      expect(result).not.toContain('onload')
      expect(result).not.toContain('onclick')
    })

    it('strips animate elements (can be abused)', () => {
      const input = '<svg><animate attributeName="x" from="0" to="100"/></svg>'
      const result = sanitizeSvg(input)
      expect(result).not.toContain('<animate')
    })
  })

  describe('containsDangerousHtml', () => {
    it('detects script tags', () => {
      expect(containsDangerousHtml('<script>alert(1)</script>')).toBe(true)
      expect(containsDangerousHtml('<SCRIPT>alert(1)</SCRIPT>')).toBe(true)
    })

    it('detects iframe tags', () => {
      expect(containsDangerousHtml('<iframe src="x">')).toBe(true)
    })

    it('detects event handlers', () => {
      expect(containsDangerousHtml('<div onclick="x">')).toBe(true)
      expect(containsDangerousHtml('<img onerror="x">')).toBe(true)
    })

    it('detects javascript: URLs', () => {
      expect(containsDangerousHtml('<a href="javascript:x">')).toBe(true)
    })

    it('returns false for safe content', () => {
      expect(containsDangerousHtml('<p>Hello world</p>')).toBe(false)
      expect(containsDangerousHtml('<a href="https://example.com">Link</a>')).toBe(false)
    })
  })

  describe('Security constants', () => {
    it('ALLOWED_TAGS does not include dangerous tags', () => {
      const dangerous = ['script', 'iframe', 'object', 'embed', 'style', 'link', 'meta', 'base']
      for (const tag of dangerous) {
        expect(ALLOWED_TAGS).not.toContain(tag)
      }
    })

    it('FORBIDDEN_ATTRS includes all event handlers', () => {
      expect(FORBIDDEN_ATTRS).toContain('onclick')
      expect(FORBIDDEN_ATTRS).toContain('onload')
      expect(FORBIDDEN_ATTRS).toContain('onerror')
      expect(FORBIDDEN_ATTRS).toContain('onmouseover')
    })
  })
})
