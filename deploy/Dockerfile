FROM python:3.13

ARG ENVIRONMENT
ENV ENVIRONMENT="${ENVIRONMENT}"

RUN apt-get update && apt-get install -y libgdal-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /code

RUN pip install --no-cache-dir --upgrade pip

COPY deploy/requirements /code/requirements

RUN pip install --no-cache-dir \
    -r requirements/base.txt -r requirements/${ENVIRONMENT}.txt

COPY deploy/logging/${ENVIRONMENT}.yml /code/config/logging.yml
COPY deploy/settings/${ENVIRONMENT}.yml /code/config/app_settings.yml
COPY deploy/colormaps/custom.json /code/config/colormaps.json
COPY deploy/metadata /code/registry
# The selected release's dataset-facts.json files, copied by `make collect-release-facts`.
COPY build/release-facts /code/release-facts

COPY timeseries/app /code/app

# Merge dataset files, the environment file, and the release's observed facts into
# the registry the API loads. Development skips data that has not been processed.
RUN python -m app.registry_build --metadata-dir /code/registry \
    --facts-dir /code/release-facts --environment "${ENVIRONMENT}" \
    --output /code/metadata.yml \
    $(if [ "${ENVIRONMENT}" = dev ]; then echo --allow-missing-facts; fi)

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--reload"]
