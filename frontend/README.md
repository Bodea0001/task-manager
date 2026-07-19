# Task Manager Frontend

Task Manager is a responsive task-management application built around two
complementary ways of working:

- direct interaction with tasks, schedules, recurring work, and tags;
- natural-language interaction through an AI assistant.

The direct interface remains the source of truth. An assistant response never
replaces confirmation that a change was saved and is visible in the relevant
workspace.

## Product Scope

The current frontend covers the complete initial workflow:

- account registration, sign-in, session restoration, and sign-out;
- task discovery, creation, editing, completion, reopening, and deletion;
- tag creation, assignment, removal, and deletion;
- weekly schedule inspection and conflict visibility;
- recurring-task creation, rule management, and instance exceptions;
- chat history and AI-assisted task operations;
- profile, language, and appearance preferences;
- desktop, tablet, and mobile layouts;
- installable Progressive Web App behavior.

The interface contains no demonstration task data. All task, tag, recurrence,
chat, and account information shown to a signed-in user comes from the backend.

## Application Layout

### Desktop

The desktop application uses three working regions:

1. A compact navigation rail for Tasks, Calendar, Recurring tasks, Chat, and
   Settings.
2. The main workspace for the selected section.
3. A persistent assistant panel beside task-oriented sections.

The navigation and assistant panel can be collapsed independently. Their state
is saved locally, allowing users to trade navigation context for additional
working space without losing an assistant draft or active conversation.

### Mobile

Mobile devices use icon-based bottom navigation so section names do not compete
with the available vertical space. The assistant opens over task-oriented
sections as a drawer and is also available through the dedicated Chat section.
The active conversation and message draft remain available when the drawer is
closed or the user moves between sections.

Creation and detail screens replace the current workspace instead of being
compressed into a narrow side panel. Closing them returns the user to the
originating section.

## Accounts And Sessions

Users can:

- register with an email address, password, and profile information;
- sign in and restore an existing session after a page reload;
- update their first, middle, and last name and email address;
- clear the optional middle name;
- sign out and revoke the current refresh token.

Access-token renewal happens automatically. A rejected access token triggers a
single coordinated refresh attempt rather than making the user sign in again.
Concurrent requests and browser tabs are coordinated where the browser supports
it, reducing the risk of invalidating a rotating refresh token more than once.

Authentication forms use localized validation while preserving browser password
generation, storage, and autofill support. Protected workspaces are not shown
until the stored session has been confirmed by the backend.

## Tasks

Tasks is the default workspace. Its initial view focuses on actionable work
without hiding tasks that have no schedule.

### Views And Organization

Users can switch between:

- **Today** for overdue work, tasks due or scheduled today, and unscheduled
  tasks;
- **Upcoming** for future work;
- **All** for the currently loaded active task set;
- **Completed** for finished tasks.

The Today view groups overdue, current-day, and unscheduled work separately.
Task rows expose the most useful information without requiring users to open
every item: title, time, priority, tags, recurrence context, and completion
state. Search matches the loaded task titles, descriptions, and tags.

### Task Lifecycle

Users can:

- create a task;
- open its details;
- change its title, description, status, priority, deadline, and schedule;
- assign or remove tags;
- complete or reopen it directly from the list;
- remove its schedule as part of the next saved change;
- delete it after explicit confirmation.

Descriptions support Markdown source and a formatted preview. Rendered Markdown
is sanitized before display. Date and time fields use a consistent localized
picker on desktop and mobile instead of relying on visually inconsistent native
browser controls.

Task edits send only actual changes. Opening a newly created task and saving it
without modifying any field does not produce a redundant update.

### Scheduling Conflicts

When a task schedule overlaps other work, the form remains open and preserves
the entered values. The error identifies the scheduling conflict and can show
the tasks responsible for it, allowing the user to make an informed correction
instead of retrying blindly.

### Tags

Tags are managed in the context of task and recurring-task editing. Users can:

- search existing tags;
- create a missing tag without leaving the form;
- attach or detach tags;
- delete a tag after reviewing a warning that it will be removed from every
  task that uses it.

Tag lists are updated locally after successful operations, avoiding unnecessary
full reloads while keeping visible task and recurrence data synchronized.

## Calendar

Calendar provides a time-based view of deadlines and scheduled work.

### Desktop Week

The desktop view displays one week on a time-scaled grid. It supports:

- movement to previous and next weeks;
- return to the current week;
- readable scheduled intervals and deadline markers;
- separate interaction with overlapping tasks;
- duration and priority information;
- conflict indicators;
- filters for time type, priority, and status;
- opening task details directly from the calendar.

The visible time range is kept practical for the work shown, reducing excessive
scrolling to evening tasks. Short or overlapping tasks remain selectable even
when the calendar has limited horizontal space.

### Mobile Day

Mobile devices show one selected day from the active week instead of shrinking
the entire weekly grid. Returning to Today selects both the current week and the
actual current day. Date and time selection uses mobile-friendly controls,
including scrollable hour and minute choices with valid-value limits.

## Recurring Tasks

The Recurring tasks workspace separates a reusable task definition from the
individual tasks produced from it.

### Recurring Definitions

Users can:

- search and inspect recurring tasks;
- create a recurring task with its first rule;
- set its description, priority, and tags;
- add and remove tags later;
- delete the recurring definition after reviewing its effect on generated
  tasks.

Deleting a recurring definition removes unfinished generated tasks while
preserving completed instances as history.

### Repeat Rules

Rules support:

- daily recurrence;
- recurrence on one or more weekdays;
- monthly recurrence by day of month;
- monthly recurrence by an ordinal weekday;
- intervals longer than one day, week, or month;
- an inclusive rule start date and required occurrence time;
- optional duration for scheduled time blocks;
- optional ending by date or number of occurrences.

Without a duration, generated tasks receive a deadline. With a duration, they
receive a scheduled start and end time.

The recurrence pattern and calendar selection are intentionally immutable after
creation. Users can still change the rule start date, occurrence time, duration,
and ending conditions. A structurally different pattern should be represented
by a new rule, avoiding silent reinterpretation of already generated work.

Deleting a rule removes its unfinished generated tasks and preserves completed
instances.

### Individual Instances

Generated instances are shown in bounded date ranges and paginated lists so a
long-running recurrence does not overwhelm the page. A user can work with one
instance independently by:

- changing its date or time;
- skipping it after confirmation;
- restoring a skipped instance.

The interface explains whether a recurrence operation affects the reusable
definition, future generated tasks, or only one instance.

## Assistant And Conversations

The assistant supports natural-language task management without replacing the
direct interface.

Users can ask the assistant to find, create, organize, or update task-related
data. While a request is running, the interface shows one concise execution
plan with step statuses. Internal tools, model names, routing decisions, and
other implementation details remain hidden.

After a successful assistant operation, the relevant task, tag, calendar, and
recurrence views refresh from authoritative backend data. This makes the visible
workspace the confirmation that the requested change was actually persisted.

### Conversation Management

Users can:

- create a conversation;
- switch between existing conversations;
- rename a conversation;
- delete a conversation and its message history after confirmation;
- incrementally load older conversations and messages;
- continue the same active conversation from the desktop panel, mobile drawer,
  or dedicated Chat section.

Only one assistant request can run in the same conversation at a time. A second
attempt receives a clear in-progress message instead of starting a competing
operation.

The composer shows the assistant allowance associated with the account. Limited
accounts see the number of requests remaining and cannot submit another request
after the allowance is exhausted. Accounts with unmetered access see a clear
unlimited-access label instead of an artificial numeric counter.

Drafts are stored independently for each user and conversation. They survive
route changes, panel collapse, and page reloads within the same browser tab, but
are removed when the authenticated session ends or the tab is closed.

Connection interruptions, coordination failures, and assistant execution
errors are presented as user-facing states with support details when available.
Recoverable input is not discarded.

## Settings And Personalization

Settings contains account and application preferences.

### Language

The complete interface is available in English and Russian. The initial
language is selected in this order:

1. A saved preference.
2. The browser language.
3. English as the fallback.

Changing the language updates the current interface without reloading the page.
Dates, times, plural forms, field labels, validation feedback, and stable API
errors follow the selected locale. User-authored task, tag, description, and
chat content is never translated automatically.

### Appearance

Users can select a light, dark, or system theme. System is the default and
continues following operating-system changes until the user chooses an explicit
theme. The preference persists across visits, and supported browsers use a
smooth whole-page transition between palettes. Reduced-motion preferences are
respected.

### Navigation Preferences

Desktop navigation and the assistant can be collapsed independently. These
preferences persist locally and do not affect the account on other devices.

## Validation, Errors, And Data Safety

Forms provide localized field-level validation and a summary when several
fields need attention. Standard browser semantics remain available for password
managers, autofill, and accessibility, while visible error text follows the
application language.

The interface follows these safeguards:

- duplicate submissions are blocked while an operation is pending;
- recoverable input remains available after validation or connection errors;
- unsaved task and recurrence forms warn before navigation or page unload;
- destructive operations require explicit confirmation;
- broad or ambiguous state changes are not guessed optimistically;
- successful operations update visible data from confirmed server responses;
- request identifiers are available in expandable technical details without
  overwhelming the primary error message;
- tokens, credentials, stack traces, and internal implementation details are
  never shown in diagnostics.

## Accessibility

Core workflows are designed for pointer, keyboard, and assistive-technology
users. The interface provides:

- visible keyboard focus;
- a skip link to the main workspace;
- predictable focus placement after navigation;
- focus restoration when detail screens, dialogs, and drawers close;
- focus containment and Escape handling in modal interfaces;
- arrow, Home, and End navigation for tab groups and custom time selectors;
- accessible names and tooltips for icon-only controls;
- reduced animation when the operating system requests reduced motion;
- equivalent core workflows on desktop and mobile.

Automated checks cover the keyboard contracts, but a manual screen-reader and
cross-browser accessibility audit remains a release activity.

## Progressive Web App And Offline Behavior

Production builds can be installed as a Progressive Web App from supporting
browsers. Installation includes application icons for common desktop, mobile,
maskable, and Apple contexts. Production installation requires HTTPS; localhost
is accepted for development testing.

After one successful online visit, the versioned application shell can open
without a network connection. Offline behavior is intentionally limited:

- static interface resources are cached;
- API responses, tokens, tasks, messages, and other user data are not placed in
  the service-worker cache;
- the interface reports lost connectivity instead of presenting server-backed
  information as current;
- changes cannot be saved while offline;
- session restoration is retried when browser connectivity returns;
- outdated application-shell caches are removed during updates.

This is an installable, connectivity-aware application, not an offline task
database.

## Current Product Limitations

The following limitations are deliberate and should be considered when planning
future work:

- Task views currently operate on the first loaded page, up to 100 tasks. Local
  search and filters cannot claim completeness beyond that page. Complete large
  datasets require server-side pagination and filtering.
- Calendar currently provides desktop week and mobile day views. Month overview,
  schedule timeline, free-time visualization, and drag-to-reschedule are not yet
  included.
- Existing recurring definitions do not yet expose direct editing of their
  title, description, and priority.
- A rule's recurrence cadence and calendar selectors cannot be changed after
  creation.
- Recurring instances are loaded through bounded windows; very large recurrence
  histories may require expanded server-side pagination later.
- Offline task reading, editing, background synchronization, reminders, and push
  notifications are not supported.
- Assistant execution requires backend and model connectivity.

## Technical Reference

This section separates implementation and operation details from the product
description above.

### Architecture

The frontend is a SolidJS single-page application built with Vite. It is stored
in the same repository as the backend but can be built and deployed
independently. Browser routes select workspaces without performing full-page
reloads, while protected data is retrieved from the Task Manager HTTP API.

The source tree follows these responsibility boundaries:

- **Application** composes global providers, routing, protected layout, and
  shared visual foundations.
- **Pages** represent complete route-level workspaces such as Tasks, Calendar,
  Recurring tasks, Chat, and Settings.
- **Features** contain complete user workflows such as authentication, task
  creation, recurrence editing, and assistant interaction.
- **Entities** define frontend representations of backend resources and their
  server-state operations.
- **Shared** contains reusable API, authentication, localization, theme,
  navigation, form, and interface infrastructure.

Server state is coordinated through a shared query cache so a confirmed change
can update every affected workspace without reloading the application. Local
interface preferences are kept separately from server-owned data. Conversation
drafts are scoped to the authenticated user and browser tab.

English and Russian dictionaries are bundled with the application to avoid
runtime translation downloads. Production builds add the web manifest,
generated platform icons, and service worker; development builds do not install
a service worker.

The browser communicates with relative `/api` and `/health` paths. In local
development Vite proxies these paths to the configured backend. In production,
the web server or reverse proxy must route frontend assets and backend paths to
their respective services under the same public origin.

### Environment

Use the Node version declared by the frontend and install its dependencies:

```bash
nvm use
npm install
```

Copy `.env.example` to `.env.local` when the backend is not available at the
default local address. The development proxy target can then be changed without
altering tracked project files.

### Commands

| Command | Purpose |
| --- | --- |
| `nvm use` | Activate the frontend Node version. |
| `npm install` | Install dependencies using the project's lock file. |
| `npm run dev` | Start the development server with backend proxying. |
| `npm run build` | Type-check and create the production application in `dist`. |
| `npm run preview -- --host 0.0.0.0` | Serve the compiled `dist` application for local inspection. |
| `npm run lint` | Check source and configuration files with ESLint. |
| `npm test` | Run the complete frontend test suite once. |
| `npm run test:watch` | Run tests continuously while developing. |
| `npm run check:bundle` | Check the existing production build against gzip-size budgets. |
| `npm run check:performance` | Create a production build and then verify its size budgets. |

The preview server does not proxy API requests. Full preview testing therefore
requires the frontend and backend to be exposed through the same reverse proxy
or an equivalent deployment setup.

### Performance Budgets

The production bundle is checked against these limits:

- largest JavaScript asset: 170 KiB gzip;
- total JavaScript: 220 KiB gzip;
- total CSS: 25 KiB gzip.

The budgets include deliberate headroom above the current build and should only
be increased for a measured product reason.
