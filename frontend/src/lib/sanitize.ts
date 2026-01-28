/**
 * HTML Sanitization utilities for safe rendering of user/agent content.
 *
 * Security Policy:
 * - Whitelist approach: only explicitly allowed tags/attributes pass through
 * - Scripts, iframes, and event handlers are ALWAYS stripped
 * - SVG is allowed but heavily restricted (no scripts, no foreignObject)
 */

import DOMPurify from 'dompurify'

/**
 * Allowed HTML tags for general content.
 * Follows a minimal, security-first approach.
 */
export const ALLOWED_TAGS = [
  // Text structure
  'p', 'br', 'hr',
  // Text formatting
  'b', 'i', 'strong', 'em', 'u', 's', 'mark', 'small', 'sub', 'sup',
  // Lists
  'ul', 'ol', 'li',
  // Tables
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col',
  // Code
  'code', 'pre', 'kbd', 'samp', 'var',
  // Links
  'a',
  // Block elements
  'div', 'span', 'blockquote',
  // Headings
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  // Definition lists
  'dl', 'dt', 'dd',
  // Details/summary
  'details', 'summary',
  // Figure
  'figure', 'figcaption',
]

/**
 * Allowed SVG tags (subset for diagrams).
 * Strictly no scripting elements.
 */
export const ALLOWED_SVG_TAGS = [
  'svg',
  // Container elements
  'g', 'defs', 'symbol', 'use', 'clipPath', 'mask', 'marker',
  // Shape elements
  'circle', 'ellipse', 'line', 'path', 'polygon', 'polyline', 'rect',
  // Text elements
  'text', 'tspan', 'textPath',
  // Gradient elements
  'linearGradient', 'radialGradient', 'stop',
  // Filter elements (safe subset)
  'filter', 'feGaussianBlur', 'feOffset', 'feBlend', 'feFlood', 'feComposite',
  'feMerge', 'feMergeNode', 'feColorMatrix', 'feDropShadow',
  // Other
  'title', 'desc', 'pattern', 'image',
]

/**
 * Allowed HTML attributes.
 * No event handlers (on*), no dangerous attributes.
 */
export const ALLOWED_ATTRS = [
  // Global attributes
  'id', 'class', 'title', 'lang', 'dir', 'hidden', 'tabindex', 'aria-*', 'data-*',
  // Link attributes
  'href', 'target', 'rel',
  // Table attributes
  'colspan', 'rowspan', 'scope', 'headers',
  // Form-related (read-only display)
  'disabled', 'readonly',
  // List attributes
  'start', 'type', 'reversed',
  // Details
  'open',
]

/**
 * Allowed SVG attributes.
 * Presentation attributes only, no scripting.
 */
export const ALLOWED_SVG_ATTRS = [
  // Core attributes
  'id', 'class', 'lang',
  // Presentation attributes
  'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
  'stroke-dasharray', 'stroke-dashoffset', 'stroke-opacity', 'fill-opacity',
  'opacity', 'transform', 'font-family', 'font-size', 'font-weight', 'font-style',
  'text-anchor', 'dominant-baseline', 'alignment-baseline',
  // Positioning
  'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r', 'rx', 'ry',
  'width', 'height', 'viewBox', 'preserveAspectRatio',
  // Path
  'd', 'points',
  // Gradient
  'offset', 'stop-color', 'stop-opacity', 'gradientUnits', 'gradientTransform',
  'spreadMethod', 'fx', 'fy',
  // Clip/Mask
  'clip-path', 'clip-rule', 'mask',
  // Filter
  'filter', 'flood-color', 'flood-opacity', 'in', 'in2', 'result', 'stdDeviation',
  'dx', 'dy', 'mode', 'values', 'type',
  // Marker
  'marker-start', 'marker-mid', 'marker-end', 'markerWidth', 'markerHeight',
  'markerUnits', 'orient', 'refX', 'refY',
  // Pattern
  'patternUnits', 'patternContentUnits', 'patternTransform',
  // Use/Symbol
  'href', 'xlink:href',
  // Image (URLs only, validated separately)
  // 'href' already included
]

/**
 * Attributes that should never be allowed (explicitly blocked).
 */
export const FORBIDDEN_ATTRS = [
  // Event handlers - these should NEVER pass through
  'onabort', 'onafterprint', 'onbeforeprint', 'onbeforeunload', 'onblur',
  'oncanplay', 'oncanplaythrough', 'onchange', 'onclick', 'oncontextmenu',
  'oncopy', 'oncuechange', 'oncut', 'ondblclick', 'ondrag', 'ondragend',
  'ondragenter', 'ondragleave', 'ondragover', 'ondragstart', 'ondrop',
  'ondurationchange', 'onemptied', 'onended', 'onerror', 'onfocus',
  'onhashchange', 'oninput', 'oninvalid', 'onkeydown', 'onkeypress', 'onkeyup',
  'onload', 'onloadeddata', 'onloadedmetadata', 'onloadstart', 'onmessage',
  'onmousedown', 'onmousemove', 'onmouseout', 'onmouseover', 'onmouseup',
  'onmousewheel', 'onoffline', 'ononline', 'onpagehide', 'onpageshow', 'onpaste',
  'onpause', 'onplay', 'onplaying', 'onpopstate', 'onprogress', 'onratechange',
  'onreset', 'onresize', 'onscroll', 'onsearch', 'onseeked', 'onseeking',
  'onselect', 'onstalled', 'onstorage', 'onsubmit', 'onsuspend', 'ontimeupdate',
  'ontoggle', 'onunload', 'onvolumechange', 'onwaiting', 'onwheel',
  // Dangerous attributes
  'formaction', 'xlink:actuate', 'xmlns:xlink',
]

/**
 * Configure DOMPurify with our security policy.
 */
function configurePurify() {
  // Hook to remove dangerous tags that might slip through
  DOMPurify.addHook('uponSanitizeElement', (node, data) => {
    const dangerousTags = ['script', 'iframe', 'object', 'embed', 'applet', 'frame', 'frameset']
    if (dangerousTags.includes(data.tagName.toLowerCase()) && node.parentNode) {
      node.parentNode.removeChild(node)
    }
  })

  // Hook to remove any remaining event handlers (belt and suspenders)
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    // Remove any on* attributes that might have slipped through
    const attrs = node.attributes
    if (attrs) {
      for (let i = attrs.length - 1; i >= 0; i--) {
        const attr = attrs[i]
        if (attr.name.toLowerCase().startsWith('on')) {
          node.removeAttribute(attr.name)
        }
      }
    }

    // Force links to open safely
    if (node.tagName === 'A') {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }

    // Remove javascript: URLs
    const href = node.getAttribute('href')
    if (href && /^\s*javascript:/i.test(href)) {
      node.removeAttribute('href')
    }

    // Remove data: URLs except for safe image types
    if (href && /^\s*data:/i.test(href)) {
      if (!/^\s*data:image\/(png|jpeg|gif|webp|svg\+xml);base64,/i.test(href)) {
        node.removeAttribute('href')
      }
    }
  })
}

// Configure on module load
configurePurify()

/**
 * Sanitize HTML content for safe rendering.
 *
 * @param html - Raw HTML string
 * @param options - Sanitization options
 * @returns Sanitized HTML string
 */
/**
 * Dangerous tags that must always be stripped.
 * These are stripped both via DOMPurify config and post-processing regex.
 */
const DANGEROUS_TAG_PATTERN = /<(script|iframe|object|embed|applet|frame|frameset|style|link|meta|base|form|input|textarea|select|button)[^>]*>.*?<\/\1>|<(script|iframe|object|embed|applet|frame|frameset|style|link|meta|base|form|input|textarea|select|button)[^>]*\/?>/gi

export function sanitizeHtml(
  html: string,
  options: { allowSvg?: boolean } = {}
): string {
  const tags = options.allowSvg
    ? [...ALLOWED_TAGS, ...ALLOWED_SVG_TAGS]
    : ALLOWED_TAGS

  const attrs = options.allowSvg
    ? [...ALLOWED_ATTRS, ...ALLOWED_SVG_ATTRS]
    : ALLOWED_ATTRS

  // First pass: DOMPurify sanitization
  let result = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: tags,
    ALLOWED_ATTR: attrs,
    // Explicitly forbid dangerous tags
    FORBID_TAGS: [
      'script', 'iframe', 'object', 'embed', 'applet',
      'style', 'link', 'meta', 'base',
      'form', 'input', 'textarea', 'select', 'button',
      'frame', 'frameset', 'layer', 'ilayer', 'bgsound',
    ],
    FORBID_ATTR: FORBIDDEN_ATTRS,
    ALLOW_DATA_ATTR: true,
    ALLOW_ARIA_ATTR: true,
    // Keep content of removed tags (except script)
    KEEP_CONTENT: true,
    // Don't sanitize document structure
    WHOLE_DOCUMENT: false,
    // Return string (not DOM node)
    RETURN_DOM: false,
    RETURN_DOM_FRAGMENT: false,
    // Parse as HTML (not XML)
    PARSER_MEDIA_TYPE: 'text/html',
  })

  // Second pass: regex-based removal for any tags that slipped through
  // This is belt-and-suspenders security
  result = result.replace(DANGEROUS_TAG_PATTERN, '')

  return result
}

/**
 * Sanitize SVG content specifically.
 * More restrictive than general HTML sanitization.
 *
 * @param svg - Raw SVG string
 * @returns Sanitized SVG string
 */
export function sanitizeSvg(svg: string): string {
  return DOMPurify.sanitize(svg, {
    ALLOWED_TAGS: ALLOWED_SVG_TAGS,
    ALLOWED_ATTR: ALLOWED_SVG_ATTRS,
    FORBID_TAGS: ['script', 'foreignObject', 'animate', 'animateMotion', 'animateTransform', 'set'],
    FORBID_ATTR: FORBIDDEN_ATTRS,
    // Force namespace for SVG
    NAMESPACE: 'http://www.w3.org/2000/svg',
  })
}

/**
 * Create a rehype-sanitize compatible schema.
 * This provides the same security policy for the rehype pipeline.
 */
export const rehypeSanitizeSchema = {
  tagNames: ALLOWED_TAGS,
  attributes: {
    '*': ['className', 'id', 'title', 'lang', 'dir'],
    a: ['href', 'target', 'rel'],
    td: ['colspan', 'rowspan'],
    th: ['colspan', 'rowspan', 'scope'],
    ol: ['start', 'type', 'reversed'],
    li: ['value'],
    details: ['open'],
    code: ['className'], // for language-* classes
    pre: ['className'],
    span: ['className'],
    div: ['className'],
  },
  protocols: {
    href: ['http', 'https', 'mailto'],
  },
  strip: ['script', 'style'],
  clobberPrefix: 'user-content-',
  clobber: ['name', 'id'],
}

/**
 * Check if a string contains potentially dangerous HTML.
 * Useful for logging/monitoring.
 */
export function containsDangerousHtml(html: string): boolean {
  const dangerousPatterns = [
    /<script\b/i,
    /<iframe\b/i,
    /<object\b/i,
    /<embed\b/i,
    /\bon\w+\s*=/i,
    /javascript:/i,
    /vbscript:/i,
    /<style\b/i,
    /<link\b/i,
  ]

  return dangerousPatterns.some(pattern => pattern.test(html))
}
