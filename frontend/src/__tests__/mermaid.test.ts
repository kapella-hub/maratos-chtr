import { describe, it, expect } from 'vitest'
import {
  isMermaidCode,
  isMermaidContent,
  SUPPORTED_DIAGRAM_TYPES,
  MERMAID_CONTENT_PATTERN,
} from '../components/MermaidDiagram'

describe('Mermaid Diagram Detection', () => {
  describe('isMermaidCode', () => {
    it('returns true for "mermaid" language', () => {
      expect(isMermaidCode('mermaid')).toBe(true)
    })

    it('is case-insensitive', () => {
      expect(isMermaidCode('Mermaid')).toBe(true)
      expect(isMermaidCode('MERMAID')).toBe(true)
    })

    it('returns false for other languages', () => {
      expect(isMermaidCode('javascript')).toBe(false)
      expect(isMermaidCode('python')).toBe(false)
      expect(isMermaidCode('')).toBe(false)
    })
  })

  describe('isMermaidContent', () => {
    it('detects flowchart diagrams', () => {
      expect(isMermaidContent('flowchart TB\n  A --> B')).toBe(true)
      expect(isMermaidContent('flowchart LR\n  A --> B')).toBe(true)
      expect(isMermaidContent('flowchart TD\n  A --> B')).toBe(true)
    })

    it('detects graph diagrams (legacy flowchart)', () => {
      expect(isMermaidContent('graph TD\n  A --> B')).toBe(true)
      expect(isMermaidContent('graph LR\n  A --> B')).toBe(true)
    })

    it('detects sequence diagrams', () => {
      expect(isMermaidContent('sequenceDiagram\n  A->>B: Hello')).toBe(true)
    })

    it('detects class diagrams', () => {
      expect(isMermaidContent('classDiagram\n  class Animal')).toBe(true)
    })

    it('detects state diagrams', () => {
      expect(isMermaidContent('stateDiagram-v2\n  [*] --> State1')).toBe(true)
      expect(isMermaidContent('stateDiagram\n  [*] --> State1')).toBe(true)
    })

    it('detects ER diagrams', () => {
      expect(isMermaidContent('erDiagram\n  USER ||--o{ ORDER')).toBe(true)
    })

    it('detects gantt charts', () => {
      expect(isMermaidContent('gantt\n  title Project')).toBe(true)
    })

    it('detects pie charts', () => {
      expect(isMermaidContent('pie\n  "A" : 50')).toBe(true)
    })

    it('detects journey diagrams', () => {
      expect(isMermaidContent('journey\n  title User Journey')).toBe(true)
    })

    it('detects mindmap diagrams', () => {
      expect(isMermaidContent('mindmap\n  root((Central))')).toBe(true)
    })

    it('detects timeline diagrams', () => {
      expect(isMermaidContent('timeline\n  title Timeline')).toBe(true)
    })

    it('detects gitGraph diagrams', () => {
      expect(isMermaidContent('gitGraph\n  commit')).toBe(true)
    })

    it('detects quadrant charts', () => {
      expect(isMermaidContent('quadrantChart\n  title Chart')).toBe(true)
    })

    it('detects C4 diagrams', () => {
      expect(isMermaidContent('C4Context\n  Person(user)')).toBe(true)
      expect(isMermaidContent('C4Container\n  Container(api)')).toBe(true)
    })

    it('detects sankey diagrams', () => {
      expect(isMermaidContent('sankey\n  A,B,10')).toBe(true)
    })

    it('handles leading whitespace', () => {
      expect(isMermaidContent('  flowchart TB\n  A --> B')).toBe(true)
      expect(isMermaidContent('\n\nflowchart TB\n  A --> B')).toBe(true)
    })

    it('returns false for non-mermaid content', () => {
      expect(isMermaidContent('const x = 1;')).toBe(false)
      expect(isMermaidContent('function foo() {}')).toBe(false)
      expect(isMermaidContent('# Markdown heading')).toBe(false)
    })

    it('is case-insensitive', () => {
      expect(isMermaidContent('FLOWCHART TB\n  A --> B')).toBe(true)
      expect(isMermaidContent('SequenceDiagram\n  A->>B: Hi')).toBe(true)
    })
  })

  describe('SUPPORTED_DIAGRAM_TYPES', () => {
    it('includes all common diagram types', () => {
      const expectedTypes = [
        'flowchart',
        'graph',
        'sequenceDiagram',
        'classDiagram',
        'stateDiagram',
        'erDiagram',
        'gantt',
        'pie',
        'journey',
        'mindmap',
      ]

      for (const type of expectedTypes) {
        expect(SUPPORTED_DIAGRAM_TYPES).toContain(type)
      }
    })

    it('includes C4 diagram types', () => {
      expect(SUPPORTED_DIAGRAM_TYPES).toContain('C4Context')
      expect(SUPPORTED_DIAGRAM_TYPES).toContain('C4Container')
    })
  })

  describe('MERMAID_CONTENT_PATTERN', () => {
    it('matches at start of string', () => {
      expect(MERMAID_CONTENT_PATTERN.test('flowchart TB')).toBe(true)
    })

    it('requires word boundary after type', () => {
      // "flowchartTB" is not a valid diagram start (no space)
      expect(MERMAID_CONTENT_PATTERN.test('flowchartTB')).toBe(false)
    })

    it('matches with various whitespace', () => {
      expect(MERMAID_CONTENT_PATTERN.test('flowchart\nTB')).toBe(true)
      expect(MERMAID_CONTENT_PATTERN.test('flowchart  TB')).toBe(true)
    })
  })
})

describe('Org Chart Patterns', () => {
  // These tests verify that org charts can be represented as flowcharts
  it('flowchart TB is suitable for org charts', () => {
    const orgChart = `flowchart TB
      CEO[CEO]
      CEO --> VP1[VP Engineering]
      CEO --> VP2[VP Sales]
      VP1 --> M1[Manager 1]
      VP1 --> M2[Manager 2]`

    expect(isMermaidContent(orgChart)).toBe(true)
  })

  it('mindmap is suitable for org structures', () => {
    const mindmapOrg = `mindmap
      root((Company))
        Engineering
          Frontend
          Backend
        Sales
          Enterprise
          SMB`

    expect(isMermaidContent(mindmapOrg)).toBe(true)
  })
})
