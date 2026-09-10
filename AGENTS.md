# Repository Conventions

- Use Conventional Commits: `type(scope): imperative summary`. Common types are
  `feat`, `fix`, `test`, `docs`, `refactor`, `build`, `ci`, and `chore`. Keep each
  commit to one logical change.
- Run `make test` before committing. It uses an isolated Compose project, loads
  `timeseries/app/pytest.ini`, and cleans up its test services.
- Use the Make targets as the deployment interface: `make deploy-dev`,
  `make deploy-staging`, or `make deploy-production`. Do not add back
  `./configure`, `config.mk`, or a generated root `docker-compose.yml` workflow.
- Validate Compose changes for every environment with
  `make config ENVIRONMENT={dev,staging,prod}`.
- `comses/infrastructure` is the infrastructure source of truth.
  `skope-terraform` is defunct. The managed checkout is `/srv/apps/skope-api`,
  the Compose project is `skope-api`, and the API is exposed on host port `8001`.
- Staging and production datasets live at `/srv/datasets` and are mounted
  read-only at `/data` in both the API and TiTiler containers.
- Keep service logs on stdout/stderr so Docker owns collection and rotation.
- Dataset registry changes may need matching edits in `timeseries/metadata.yml`
  and `deploy/metadata/{dev,staging,prod}.yml`.
- Keep `base_series` internal to stored jobs; status responses must not expose it.
