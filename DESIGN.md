# ice9 SDK Design Principles

## Python version support

Support as early a version of Python as we reasonably can. Python 3.9 is EOL,
so 3.10 is the floor. Move that floor up only when there is a concrete reason
to — a language feature we actually need, not one we want. Do not require users
to upgrade their runtimes to use this SDK.

No fancy syntax. No walrus operators for style points. No structural pattern
matching where a plain if/else works. No dataclass magic that obscures what is
happening. The code should be readable by anyone who knows Python, not just
people who keep up with every PEP.

## Developer experience is the priority

The SDK exists to make ice9 easy to use. Every design decision should be
evaluated first by its effect on the developer using it, not by its elegance
as library code.

The one-liner experience is the target:

```python
result = Ice9(api_key="...").analyze("photo.jpg")
print(result.nudenet)
```

If reaching that line requires reading documentation, something is wrong.
If it requires understanding the API internals, something is very wrong.

## The API supports the SDK, not the other way around

The SDK is the interface. The API is the implementation detail behind it.
When there is tension between what the API naturally exposes and what makes
sense for a developer, the API changes. The SDK does not contort itself to
match a bad API surface.

This also means: the SDK should not be a thin wrapper that re-exposes every
API field and flag verbatim. It should translate the API's internal structure
into something that makes sense to someone who has never read the API docs.

## Dynamic, not prescriptive

The API determines which services run and what results come back. The SDK does
not maintain a hardcoded list of service names or output schemas. New services
on the API become immediately accessible on the result object without an SDK
update. The SDK is a transport layer with ergonomics on top, not a schema
definition.

## Explicit failures, not silent ones

Partial results are worse than no result if the caller does not know they are
partial. When services fail, the SDK says so loudly — a warning at minimum, an
exception by default. A developer who handles `PartialResultError` has made an
explicit decision to accept partial data. A developer who never sees the failure
has no idea their nudenet result was missing.

## No unnecessary dependencies

The SDK should have as few dependencies as possible. `requests` for HTTP is
justified. Anything beyond that needs a real reason. Every dependency is a
version conflict waiting to happen in someone's project.

## Test-driven development

Tests are written before or alongside the code, not after. Every public
behavior the SDK promises — happy paths, error cases, edge conditions — has a
test that pins it down. A change that breaks a test either fixes the test
because the behavior intentionally changed, or fixes the code because it
introduced a regression.

The test suite has two layers:

**Unit tests** mock the HTTP layer and verify SDK behavior in isolation.
They run fast, require no credentials, and can be run by anyone. They cover
the full error surface: auth failures, rate limits, timeouts, partial results,
malformed responses. A unit test that only covers the happy path is not a unit
test, it is a demo.

**Integration tests** run against the real API with a real key and real images.
They verify that the SDK actually works end-to-end, not just that it sends the
right bytes. They are slower and require credentials, so they are kept separate
and not run in CI by default. Each tier gets its own integration test file.

This distinction matters: a unit test that passes does not mean the SDK works.
An integration test that passes does not mean every error path is handled. Both
are necessary.

## Keep it boring

Boring code is maintainable code. Prefer the obvious implementation. Do not
over-engineer for hypothetical future requirements. Three clear lines are better
than one clever one. If someone reads a function and immediately understands
what it does, it is well written.

## Versioning and stability

We move fast. That is a feature, not a problem — but it requires discipline
about what we promise and when we promise it.

**Before 1.0**, anything can change. We use 0.x versioning and semver loosely:
breaking changes bump the minor version (0.1 → 0.2), fixes and additions bump
the patch (0.1.0 → 0.1.1). Users who pin to a 0.x version should expect to
read the changelog on upgrade. This is the normal expectation for pre-1.0
software and we should say so clearly in the README.

**At 1.0**, the public interface is stable. After that:
- Breaking changes bump the major version (1.x → 2.0)
- New features bump the minor version (1.0 → 1.1)
- Fixes bump the patch (1.0.0 → 1.0.1)
- Deprecated interfaces get at least one minor version of warning before removal

**What counts as the public interface:**
- `Ice9` — constructor signature, `analyze()`, `tiers()`
- `AnalysisResult` — attribute access pattern, `to_dict()`, `to_json()`, `censor()`
- `ServiceResult` — `.predictions`, `.text`, `.processing_time`, `._data`
- The exception hierarchy — class names and the attributes they carry
- `CENSOR_LABELS`

**What does not count:**
- Internal methods prefixed with `_`
- The exact content of error messages
- New services appearing on the API — these are additive and not breaking

**The dynamic design is our friend here.** Because the SDK does not hardcode
service names, new API services are never a breaking change. The dangerous
direction is the SDK's own interface — that is what we protect.

**Moving fast without breaking things:** the way to ship quickly without
destabilising consumers is to add, not change. A new convenience property on
`ServiceResult` is safe. Renaming an existing one is not. When in doubt, add
the new thing and deprecate the old one rather than replacing it outright.

## The SDK owns its interface

Animal Farm owns its field names and data shapes. Windmill owns its pipeline
structure. The SDK does not file issues against them asking them to change
things for our convenience. When there is an impedance mismatch between the
raw API and what SDK callers should see, the SDK absorbs it.

Concretely: if the underlying service returns `predictions[0]["text"]` and we
want callers to write `.text`, we add a property on `ServiceResult`. We do not
ask Animal Farm to restructure their output. The boundary is clear — the SDK
is the right place to normalise presentation-layer concerns.

The corollary: when Animal Farm or Windmill make decisions about their own
contracts, we respect them. We can have opinions, but their repos are theirs.

---

## Design decisions

A running record of non-obvious choices and the reasoning behind them.
These are decisions that were debated, not ones that were obvious.

---

### `ServiceResult.text` — absorbing `predictions[0]`

VLM services return text as `predictions[0]["text"]`. The list wrapper is an
artefact of the detection service pattern (nudenet, YOLO have multiple
predictions) applied to services that always return exactly one result. Callers
should not need to know this.

Decision: add `.text` on `ServiceResult` that reads `predictions[0]["text"]`
if present, `None` otherwise. The SDK absorbs the `[0]` index so no caller
ever has to write it.

The field name stays `"text"` — not `"caption"` — because Animal Farm made
that choice deliberately. "Caption" is accurate for BLIP2/Moondream but not
for the other VLMs, which return text from a prompt. The SDK follows the same
reasoning.

---

### `to_dict()` nests services under `"services"`

Flat output (`result["nudenet"]`, `result["colors"]`) is ambiguous when service
names could collide with top-level fields like `image_id` or `services_failed`.
Nesting under `"services"` makes iteration unambiguous and the structure
self-documenting.

Pipeline bookkeeping fields (`"service"`, `"status"`) are stripped from each
service's dict — they are redundant at this level and add noise.

`processing_time` is excluded from `to_dict()` / `to_json()`. It belongs on
the `ServiceResult` object for inspection, not in serialised output. It is
infrastructure metadata, not result data.

---

### `AnalysisResult.__getattr__` returns `None` for unknown services

Unknown service names return `None` rather than raising `AttributeError`.
The rationale: the set of services that ran is API-determined, not SDK-
determined. Callers write `if result.nudenet:` naturally; an exception would
require them to check `services_submitted` before every access. `None` is the
right sentinel for "this service did not run."

Private attributes (`_anything`) still raise `AttributeError` so that Python
internals and IDE tooling work correctly.

---

### `_from_status` handles both wrapped and unwrapped service entries

Normal service results come from the results table and are wrapped by the API:
`{"data": {...}, "processing_time": ..., "result_created": ...}`. The SDK reads
`entry.get('data')` to get the service payload.

Aggregated pipeline outputs — `noun_consensus`, `verb_consensus`, `consensus`,
`caption_summary` — come from separate tables and are injected into
`service_results` directly, without the `data` wrapper. They look like:
`{"nouns": [...], "category_tally": [...], ...}`.

`_from_status` detects which shape it has: if `"data"` is a key in the entry,
use `entry["data"]`; otherwise use the entry itself as the data dict. This means
`ServiceResult` works correctly for both shapes with no special cases at the call
site.

The rule: when the API adds a new top-level field to `service_results` that
doesn't follow the standard results-table envelope, this is the one place in the
SDK that needs to know about it.

---

### `PartialResultError` carries the result

When some services fail, raising an exception with no result forces callers
to either treat partial data as total failure or catch the error and re-fetch.
Carrying the partial result on the exception lets callers make an explicit
decision: `except PartialResultError as e: result = e.result`. The failure is
loud (it is an exception) but the data is not lost.
