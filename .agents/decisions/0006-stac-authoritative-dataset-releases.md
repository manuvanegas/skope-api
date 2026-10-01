# 0006: Use STAC-Authoritative Immutable Dataset Releases

- Status: Proposed
- Date: 2026-09-11
- Revised: 2026-10-01
- Specification: [SKOPE Dataset Release Specification v1](../../docs/specs/dataset-release-v1.md)
- Supersedes, on acceptance: [0001: Separate Dataset Metadata From Storage Lookups](0001-dataset-registry-and-lookup-contract.md)
- Amends, on acceptance: [0002: Mediate COG Tiles Through Skope API](0002-api-mediated-cog-tiles.md)

## Context

SKOPE currently duplicates dataset metadata across API and ingest YAML files.
The ingest pipeline mutates one of those files with observed raster facts, emits
one STAC Collection per variable, and generates `lookup.json` as the API's
storage index. Existing output files can be reused by filename without proving
their identity or validity.

PR 48 proposes splitting curated metadata by dataset, recording observed facts
in `dataset-facts.json`, composing packages across partial variable runs, and
building the API registry from curated files plus release facts. The `titiler`
branch separately adds per-variable temporal endpoint validation and a complete
whole-migration preflight before transformation. Both bodies of work expose the
need for an explicit authority model, byte validation, and transactional release
publication.

Review of the initial proposal identified three additional boundaries that the
architecture must make explicit: temporal assets need a standard band-to-time
mapping that a client can resolve without a separate index file; planned output
properties must not be confused with observations of final bytes; and static
rasters must not be forced through temporal-cube requirements.

A second review identified two more. First, a release serves two audiences — the
SKOPE application and external researchers — and the application's needs must be
a stated, generated consequence of the release rather than a parallel curated
document. Second, a release and an application build change on different
cadences: data changes in months or years, while presentation changes with a
build. Anything on the faster cadence that is stored inside an immutable release
forces either a needless republication of unchanged data or a forbidden
mutation.

A third review settled release granularity. A release packages one dataset, not
the whole corpus. Datasets are authored, reviewed, and revised independently, so
a corpus-wide package would force republication of unchanged datasets whenever
one changed and would let one dataset's validation failure block publication of
the rest. This decides two things that a corpus-wide package had been answering
implicitly: what a deployment serves, and where an external client starts
looking.

STAC 1.1.0 and its Projection, File Info, Scientific Citation, Raster,
Datacube, Versioning, and Processing extensions provide standards-based homes
for most published metadata. COG headers remain the direct description of the
encoded raster bytes. Release completion and integrity are operational facts,
not geospatial metadata.

## Proposed decision

Subject to approval of the linked specification:

- STAC Collections and Items will be the published metadata authority.
- COG headers will be authoritative for byte-level raster properties, including
  grid, encoding, nodata, scale, offset, band descriptions, and embedded
  statistics. Corresponding STAC fields will be validated projections of those
  facts.
- A release will package exactly one dataset. Its root STAC object will be that
  dataset's Collection: a Catalog carries none of `license`, `providers`,
  `extent`, `keywords`, `summaries`, `assets`, or `item_assets`, so a Catalog at
  dataset level would strand or duplicate every dataset-level curated field,
  while a Collection is already a valid Catalog.
- A release will carry exactly one manifest, at its root, containing integrity,
  provenance, object inventory, release identity, and completion state only. It
  will not duplicate geospatial or statistical metadata.
- An aggregate release composed of other releases will not be defined. It would
  publish no bytes of its own while creating a second identity over content that
  already has an immutable one. The two needs it appears to serve are met
  separately: a deployment records the release set it serves as a
  version-controlled pin of release ID and declaration digest per dataset, and
  external discovery is a mutable STAC Catalog published outside any release,
  generated from a version-controlled listing record and naming each listed
  release's ID and digest. The pin also records the digest of each release's
  manifest file, which identifies the published bytes. A release build will not
  write to that catalog; listing is a separate reviewed act.
- A release identifier will carry its dataset identifier, so it is unique
  without contextual qualification. It will not be a dataset version: a
  repackaging change such as a different chunk size produces a new release of
  the same dataset version.
- Each release will carry one generated overview, compacted from its validated
  STAC as the final step of its build, serving both a human reader and the
  application. It will record the release ID and declaration digest it came
  from and be verified against the deployment's pin before serving. The
  application will read the overviews of its pinned release set once at startup
  and serve them composed without modification.
- The time-to-band mapping will be a rule in that overview, from which the COG
  path and one-based band index of any timestep are computed. Because variables
  of one dataset share a temporal axis and chunk boundaries, the axis and the
  chunk size are recorded once per dataset. Paths will not be stored, because
  the Item ID and COG filename conventions already determine them. An axis will
  declare itself regular (origin, step, count) or enumerated (an ordered list of
  timesteps), which changes only how a position converts to a timestep; chunking
  is defined in index space and is identical for both. A request falling between
  the steps of a regular axis will be rejected rather than rounded. The rule
  will be verified during the build against ordered STAC Band names and actual
  COG band counts. `lookup.json` will not be emitted, and a rule that disagrees
  with the bytes will fail the build rather than produce a different artifact.
- The typed model will have an immutable `ValidatedBuildPlan` consumed by the
  COG writer and a separate immutable `FinalObservation` consumed by metadata
  serializers after byte inspection.
- Dataset releases will declare either a temporal-cube or static-raster profile;
  SRTM will not acquire synthetic scientific time metadata for API convenience.
- Published releases will be immutable and selected only after a valid release
  manifest acts as the publication commit marker. One build invocation may
  request several datasets, but such an invocation is a batch rather than a
  package: it produces one independent release per dataset and is given no
  identifier, digest, manifest, or combined rollback of its own.
- Curated human-authored metadata will be compiled to STAC and will not contain
  observed raster facts. Its authoring form will be one `curated.yml` per
  dataset, and no published counterpart will be emitted: everything a consumer
  needs will be in the STAC Collection, with SKOPE-specific fields under the
  `skope:` prefix.
- Presentation will not be a release artifact. It will live in the skope-api
  repository, in one display-preferences document and the palette document it
  references (`deploy/display/`), because it is an opinion about display rather
  than a property of the data and it changes on the application's cadence. This
  covers colormaps, colour stops, visualization ranges, legends, and ticks, and
  equally dataset sort order, initial map camera, default variable selection,
  variable order, and dataset outline drawing: the cadence argument does not
  distinguish between them. Every published field will describe the data. The
  API will serve explicit rendering and legend fields, and clients will not
  compute their own ranges or apply global multipliers. Ordering will be
  explicit rather than implied by document order.
- TiTiler will remain internal and API-mediated (ADR 0002). The public metadata
  and time parameters will change in one coordinated API/UI cutover, with no
  compatibility period.

## Consequences

- A dataset release can be validated and understood independently of an API
  image or mutable registry file.
- The ingest workflow needs a typed observation model and strict agreement
  checks among COG bytes, STAC, the derived time-to-band rule, and the release
  manifest.
- Local publication needs same-filesystem staging and atomic rename. Object
  storage needs a manifest-last commit protocol because it has no multi-object
  transaction.
- One logical dataset version is represented by one Collection; temporal Items
  align variable assets by chunk.
- A presentation change never requires a new release, but the API and SKOPE UI
  must migrate together to serve and consume explicit rendering fields.
- A release is read through its manifest and STAC tree, and because it packages
  one dataset it stays self-describing when relocated on its own.
- One dataset changing does not republish the others, and one dataset failing
  preflight or validation does not block publication of the rest. Migration of
  the four datasets can still proceed in one pass.
- Choosing which datasets a deployment serves becomes an explicit, reviewed pin
  rather than an implicit consequence of what a corpus-wide release contained.
  A consistency check spanning datasets, if one is ever needed, belongs at that
  composition step, because a release build sees one dataset.
- Nothing carries a single identity for all SKOPE data at a given time. If a
  citable corpus-level identity is later required, it should be minted against
  the published catalog rather than by reintroducing an aggregate release.
- The application depends on releases only through their generated overviews, so
  the release-to-application data flow must be specified and tested rather than
  left to a curated document maintained beside the data. Because the overview is
  generated and byte-compared rather than authored, it can serve a human reader
  without becoming a second authority that can drift from STAC.
- Candidate STAC extensions require pinned versions and serialization adapters.
- Ambiguous legacy scientific fields require human review rather than automatic
  interpretation.
- Non-publishing experiments may gather evidence for unresolved decisions, but
  their artifacts cannot become releases or production dependencies without
  approval.
- On acceptance, this ADR supersedes ADR 0001 at the coordinated cutover
  (specification MIG-002): `lookup.json` and the checked-in registries are
  replaced by release overviews and per-environment release pins. It amends
  ADR 0002's public tile contract, whose `year` parameter becomes a canonical
  timestep key; TiTiler stays internal.

## Approval gate

This ADR remains Proposed. No production implementation phase may begin until
the linked specification's unresolved decisions are reviewed and this ADR is
accepted or revised. The specification's isolated, non-publishing Phase 0
experiments may run solely to gather decision evidence.
