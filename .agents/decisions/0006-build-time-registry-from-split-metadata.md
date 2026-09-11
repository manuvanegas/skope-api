# 0006: Build the Registry at Image Build Time From Dataset Files and the Selected Release

- Status: Accepted
- Date: 2026-09-11
- Supersedes: the "Registry changes may require corresponding edits in several files" consequence of 0001

## Context

The registry mixed three kinds of information with different owners: descriptions written by people, facts observed in the processed data (CRS, transform, timespan, value ranges), and the choice of datasets each environment exposes. It was duplicated across `timeseries/metadata.yml` and `deploy/metadata/{dev,staging,prod}.yml`, and the ingest pipeline wrote observed facts back into its own copy, so every dataset update required hand-merging into several multi-dataset files. The data release an environment mounted was chosen at deploy time, outside git, so nothing recorded which data a deployed commit served.

## Decision

- `deploy/metadata/datasets/<id>.yml` describes a dataset and all of its variables.
- `deploy/metadata/{dev,staging,prod}.yml` names the environment's data release (`release:`) and lists explicitly which datasets and variables it publishes.
- The ingest pipeline writes the observed facts into each package as `<id>/dataset-facts.json`. They exist only there, in the data they describe.

`make` reads `release:` to mount that release at `/data` and copies its `dataset-facts.json` files into the build context. The API image build runs `python -m app.registry_build` to merge everything into the single `/code/metadata.yml` the API already loads.

Every published variable must be described and have processed data. Observed fields may not appear in dataset files, and the described timespan must match the observed one. Any violation fails the build with a message naming the files; processed data is never touched. Development builds skip unprocessed data with a warning instead.

## Consequences

- A commit determines both the registry and the mounted data, provided releases are never modified once created. Changing data, promoting to production, and rolling back are commits.
- The image cannot disagree with its data: both come from the same release at build time.
- Staging and production images can only be built on a host that has the selected release. CI and fresh development checkouts build without facts and serve only what they have processed.
- The API loader and `/metadata` are unchanged.
- Pull requests that change data show a release path change rather than changed values.
