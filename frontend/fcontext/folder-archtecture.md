# Frontend Architecture Guide

> **Purpose:** This document defines the frontend architecture, folder responsibilities, and dependency rules for this project. Every developer and AI agent **must** follow these boundaries. Consistency, scalability, and maintainability are more important than convenience.

---

# Core Philosophy

This project follows a **feature-driven architecture** with a strict separation between:

- Routing
- UI
- Business Logic
- State Management
- API Communication
- Infrastructure

The primary goal is to ensure:

- High maintainability
- Maximum code reuse
- Minimal prop drilling
- Clear ownership of logic
- Easy onboarding for developers
- Predictable project structure
- Scalable architecture for large applications

---

# High Level Architecture

```
Page

↓

Feature Component

↓

Feature Hook

↓

Feature Service

↓

Axios Client (lib)

↓

Backend API
```

or more generally

```
Shared UI

↓

Feature Components

↓

Feature Hooks

↓

Feature Services

↓

Shared Infrastructure (lib)

↓

External Services
```

Each layer has a single responsibility.

No layer should bypass another layer.

---

# Dependency Rules

Dependencies must only flow downward.

```
app
    ↓

components
    ↓

features/components
    ↓

features/hooks
    ↓

features/services
    ↓

lib
```

## Allowed

- Feature components can use shared UI.
- Feature hooks can call services.
- Services can use lib.
- Pages can render feature components.

## Not Allowed

❌ Shared UI importing feature logic

❌ Shared UI calling APIs

❌ Components directly calling axios

❌ Components containing business logic

❌ Pages containing business logic

❌ Services importing React components

❌ Feature A tightly depending on Feature B internals

If something becomes reusable across multiple features, move it into a shared location.

---

# Folder Responsibilities

---

# app/

## Purpose

Contains only Next.js routing.

Responsible for:

- Routes
- Layouts
- Loading states
- Error boundaries
- Route organization

Page files should stay extremely lightweight.

Example:

```tsx
export default function DashboardPage() {
    return <DashboardScreen />;
}
```

The page should not contain:

- API calls
- Business logic
- Complex state
- Large JSX
- Data transformation

Its responsibility is routing only.

---

# components/

Contains reusable UI.

There are only two folders.

```
components/

    ui/

    sharedUI/
           |-functionalComponent/
           |-dumbComponent/
```

---

## ui/

Contains only Shadcn UI components.

Examples

```
Button
Dialog
Dropdown
Input
Textarea
Card
Avatar
Tabs
Popover
```

Never modify these unnecessarily.

Treat them as the design system.

---

## sharedUI/

Contains reusable application UI. and segregating on terms of functional or not so while chnaging anything the severity can be determined (if any constants thing or array of shared functional component is there it should be inside constant folder inside lib folder)

Examples

```
DataTable
PageHeader
SearchInput
Pagination
LoadingSpinner
EmptyState
DeleteDialog
FormSection
StatCard
```

Rules

These components:

- are reusable
- contain no business logic
- contain no API logic
- contain no feature-specific state

Think of them as intelligent Lego blocks.

If two pages need the same UI, it belongs here.

Never duplicate UI across features.

---

# features/

Contains the application's business domains.

Every feature owns its own logic.

Example

```
features/

    missionCommand/

    investigation/

    changeDetection/

    evidenceExplorer/

    auth/
```

Each feature should be self-contained.

Example

```
investigation/

    components/

    hooks/

    services/

    store/

    schemas/

    types/
```

---

## components/

Feature-specific UI.

These components belong only to this feature.

Examples

```
InvestigationMap

ExecutionTrace

ConfidencePanel

EvidenceCard
```

They may use:

- shared-ui
- feature hooks
- feature state

They should not call APIs directly.

---

## hooks/

Contains business logic.

This is where feature behavior lives.

Examples

```
useInvestigation()

useMissions()

useChangeDetection()

useUploadImagery()
```

Responsibilities

- fetching data
- mutations
- state composition
- memoization
- derived state
- interaction logic

Hooks call services.

Hooks never call axios directly.

---

## services/

Responsible for API communication.

Services know how to talk to the backend.

Example

```
investigation.service.ts

mission.service.ts

changeDetection.service.ts
```

Responsibilities

- GET requests
- POST requests
- PATCH requests
- DELETE requests
- request formatting
- response transformation if needed

Services use the shared axios client from lib.

No React logic belongs here.

---

## store/

used to avoid prop drilling inside a small feature or for global state management 

---

## schemas/

Contains Zod schemas.

Responsibilities

- form validation
- client-side validation
- request validation
- response validation when needed

Example

```
LoginSchema

UploadImagerySchema

MissionConfigSchema
```

---

## types/

Contains TypeScript definitions.

Examples

```
Investigation

Mission

ChangeResult

EvidenceItem

APIResponse

AnalysisOutput
```

Only keep feature-related types here.

---

# hooks/

Root-level reusable hooks.

These hooks are completely generic.

Examples

```
useDebounce()

useInfiniteScroll()

useMediaQuery()

useResponsive()

useWebSocket()

useOutsideClick()
```

Rules

They should never know about:

- investigations
- missions
- change detection
- evidence

If a hook is feature-specific, it belongs inside that feature.

---

# store/

Global Zustand store.

Contains only truly global state.

Examples

```
Auth

Sidebar

Notifications

Theme

WebSocket

User Session
```

Do not place feature state here unless it is shared across multiple independent features.

The goal is to minimize unnecessary global state.

---

# lib/

Shared infrastructure.

Everything here powers the application.

Nothing here knows about business logic.

Examples

```
Axios Client

Query Client

WebSocket Client

Environment Config

Authentication Helpers

Constants

Providers
```

This folder is responsible for initializing systems.

It should never contain feature logic.

---

## Axios Client

A single configured axios instance.

Responsibilities

- interceptors
- authentication
- refresh token
- common headers
- base URL

Every service should use this client.

Never create multiple axios instances across features.

---

## Query Client

Contains TanStack Query configuration.

Examples

```
QueryClient

default options

retry configuration

cache policies
```

---

## Authentication Helpers

Shared authentication utilities.

Examples

```
token helpers

cookie helpers

session helpers
```

---

## Environment Configuration

Responsible for reading and validating environment variables.

---

## Constants

Application-wide constants.

Examples

```
Routes

Roles

Permissions

Query Keys

Storage Keys
```

Avoid magic strings throughout the project.

---

## Providers

Contains application providers.

Examples

```
Theme Provider

Query Provider

Authentication Provider

Toast Provider
```

The application layout should simply compose these providers.

---

# State Management Guidelines

Feature state

↓

Feature state folder

Global application state

↓

store/

Infrastructure state

↓

lib/

Keep state as local as possible.

Only move state upward when multiple unrelated features require it.

---

# API Flow

Never perform API calls inside components.

Correct flow

```
Component

↓

Hook

↓

Service

↓

Axios Client

↓

Backend
```

Example

```
Investigation Component

↓

useInvestigation()

↓

investigation.service.ts

↓

axiosClient.get(...)
```

This separation makes testing, maintenance, and future changes significantly easier.

---

# Component Rules

A component should primarily focus on rendering UI.

Good components:

- receive props
- display UI
- trigger callbacks
- remain reusable

Avoid placing:

- API calls
- heavy business logic
- complex data transformations

inside components.

Move those responsibilities into hooks.

---

# Hook Rules

Hooks are responsible for application behavior.

Typical responsibilities include:

- fetching data
- handling mutations
- composing state
- memoization
- filtering
- pagination
- optimistic updates
- business workflows

Hooks should remain focused on one responsibility.

---

# Service Rules

Services are the application's communication layer.

A service should never:

- render UI
- access the DOM
- depend on React

Services only know how to communicate with external systems.

---

# Reusability Rules

Before creating a new component, ask:

> Can this be reused somewhere else?

If yes

→ move it into `components/sharedUI`

If not

→ keep it inside the feature.

Never duplicate identical UI across multiple features.

---

# Golden Rules

## Keep pages lightweight

Pages are route entry points only.

---

## Keep UI reusable

Shared UI belongs in `components/sharedUI`.

---

## Keep business logic inside hooks

Components should not contain application logic.

---

## Keep API logic inside services

Never call axios directly from a component or hook.

---

## Keep infrastructure inside lib

Infrastructure should never know about business domains.

---

## Keep state close to where it is used

Only make state global when absolutely necessary.

---

## Never violate dependency flow

Always follow

```
Page

↓

Feature Component

↓

Feature Hook

↓

Feature Service

↓

Shared Infrastructure

↓

Backend
```

This architecture is the standard that every contributor and AI agent must follow. Any new code should respect these boundaries to maintain a scalable, predictable, and maintainable codebase.