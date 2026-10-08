# Distribution and dependencies

First-party runtime, UI and review schema are distributed under LICENSE.
The distribution uses an explicit source allowlist. Private design notes,
session transcripts, local state, credentials, owner Skills and Provider
configuration are not included. The unrelated Sites deployment scaffold is
not distributed because its reuse license has not been established.

Direct runtime dependencies: FastAPI (MIT), Uvicorn (BSD-3-Clause),
jsonschema (MIT), React/React DOM (MIT), lucide-react (ISC).
Build/test dependencies include Vite and its React plugin (MIT), TypeScript
(Apache-2.0), Vitest (MIT), jsdom (MIT), Testing Library (MIT), pytest (MIT),
HTTPX (BSD-3-Clause), Hatchling (MIT). Locks retain package versions.
Each dependency retains its own license; this project's MIT license does not
relicense dependency code. Built bundles preserve generated license comments.
The source release does not redistribute owner Skill implementations.
