"""Shared diagram and rich content instructions for agents.

This module provides consistent instructions for generating diagrams and
HTML content that renders safely in the frontend.
"""

DIAGRAM_INSTRUCTIONS = """
## Diagrams and Visualizations

When users ask for diagrams, flowcharts, org charts, or visualizations, you MUST output them as **Mermaid code blocks**. The frontend automatically renders these as interactive SVG diagrams.

### Supported Diagram Types

| Type | Use For | Syntax Start |
|------|---------|--------------|
| `flowchart` | Org charts, process flows, decision trees | `flowchart TB` or `flowchart LR` |
| `sequenceDiagram` | API calls, message flows, interactions | `sequenceDiagram` |
| `classDiagram` | UML class diagrams, data models | `classDiagram` |
| `stateDiagram` | State machines, workflows | `stateDiagram-v2` |
| `erDiagram` | Database schemas, entity relationships | `erDiagram` |
| `gantt` | Project timelines, schedules | `gantt` |
| `mindmap` | Ideas, hierarchies, brainstorming | `mindmap` |
| `journey` | User journeys, experience maps | `journey` |
| `pie` | Distribution, proportions | `pie` |
| `gitGraph` | Branch visualization | `gitGraph` |

### Example: Org Chart

When asked "show me the org structure" or "create an org chart":

```mermaid
flowchart TB
    CEO[CEO<br/>Jane Smith]

    CEO --> CTO[CTO<br/>Engineering]
    CEO --> CFO[CFO<br/>Finance]
    CEO --> COO[COO<br/>Operations]

    CTO --> EM1[Engineering Manager<br/>Frontend]
    CTO --> EM2[Engineering Manager<br/>Backend]
    CTO --> EM3[Engineering Manager<br/>Platform]

    EM1 --> FE1[Senior Engineer]
    EM1 --> FE2[Engineer]
    EM2 --> BE1[Senior Engineer]
    EM2 --> BE2[Engineer]
```

### Example: Service Architecture

When asked "show the architecture" or "service flow diagram":

```mermaid
flowchart LR
    subgraph Client
        Web[Web App]
        Mobile[Mobile App]
    end

    subgraph Gateway
        API[API Gateway]
        Auth[Auth Service]
    end

    subgraph Services
        Users[User Service]
        Orders[Order Service]
        Payments[Payment Service]
    end

    subgraph Data
        DB[(PostgreSQL)]
        Cache[(Redis)]
        Queue[(RabbitMQ)]
    end

    Web --> API
    Mobile --> API
    API --> Auth
    Auth --> Users
    API --> Orders
    API --> Payments
    Orders --> Queue
    Queue --> Payments
    Users --> DB
    Orders --> DB
    Payments --> DB
    Users --> Cache
```

### Example: Sequence Diagram

When asked "show the flow" or "how does X call Y":

```mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant A as Auth Service
    participant U as User Service
    participant D as Database

    C->>G: POST /login
    G->>A: Validate credentials
    A->>U: Get user details
    U->>D: Query user
    D-->>U: User data
    U-->>A: User info
    A->>A: Generate JWT
    A-->>G: JWT token
    G-->>C: 200 OK + token
```

### Example: Mind Map

When asked "brainstorm" or "map out ideas":

```mermaid
mindmap
    root((Project))
        Frontend
            React
            TypeScript
            TailwindCSS
        Backend
            FastAPI
            PostgreSQL
            Redis
        DevOps
            Docker
            GitHub Actions
            AWS
        Testing
            pytest
            Playwright
            Jest
```

### Example: State Diagram

When asked "show states" or "workflow states":

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Review: Submit
    Review --> Approved: Approve
    Review --> Draft: Request Changes
    Approved --> Published: Publish
    Published --> Archived: Archive
    Archived --> [*]
```

### Direction Modifiers

- `TB` / `TD` - Top to Bottom (best for org charts)
- `BT` - Bottom to Top
- `LR` - Left to Right (best for process flows)
- `RL` - Right to Left

### Rules for Diagrams

1. **Always use mermaid code fences** - Never use ASCII art
2. **Choose the right diagram type** - Org charts → `flowchart TB`, sequences → `sequenceDiagram`
3. **Keep it readable** - Split large diagrams into multiple smaller ones
4. **Use subgraphs for grouping** - Makes complex diagrams clearer
5. **Add labels** - Use descriptive node and edge labels
"""

HTML_CONTENT_INSTRUCTIONS = """
## HTML Content Guidelines

When outputting HTML (tables, formatted content), use ONLY these allowed tags:

**Allowed tags:**
- Text: `p`, `br`, `strong`, `em`, `b`, `i`, `u`, `s`, `mark`, `small`, `sub`, `sup`
- Lists: `ul`, `ol`, `li`, `dl`, `dt`, `dd`
- Tables: `table`, `thead`, `tbody`, `tr`, `th`, `td`
- Code: `code`, `pre`, `kbd`
- Links: `a` (with `href` only - no javascript:)
- Block: `div`, `span`, `blockquote`
- Headings: `h1`-`h6`

**NEVER output:**
- `<script>` tags
- `<style>` tags
- `<iframe>` tags
- Event handlers (`onclick`, `onload`, etc.)
- `javascript:` URLs

**Prefer Markdown over HTML when possible** - the renderer handles markdown natively.
"""

def get_diagram_instructions() -> str:
    """Get the full diagram instructions for agent prompts."""
    return DIAGRAM_INSTRUCTIONS

def get_html_instructions() -> str:
    """Get HTML content guidelines for agent prompts."""
    return HTML_CONTENT_INSTRUCTIONS

def get_rich_content_instructions() -> str:
    """Get combined diagram and HTML instructions."""
    return DIAGRAM_INSTRUCTIONS + "\n" + HTML_CONTENT_INSTRUCTIONS
